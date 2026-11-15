"""A rule-based extractor for "Label: value" term sheets.

It is the safety net when the model is unavailable or leaves a field empty, and it makes the
extraction testable without a GPU. It reads only simple labelled lines.
"""

import re
from datetime import date, datetime

from app.common.isin import is_valid_isin
from app.termsheets.languages import CURRENCY_NAMES, LABELS, month_number, to_float
from app.termsheets.models import TermSheetRecord

# Label spellings per field. Real Final Terms use longer legal names, so those are listed too.
_LABELS: dict[str, tuple[str, ...]] = {
    "issuer": ("issuer", "borrower"),
    "isin": ("isin", "isin code"),
    "currency": ("currency", "specified currency", "specified currency or currencies"),
    "size": (
        "size",
        "aggregate nominal amount",
        "aggregate nominal amount of notes",
        "aggregate principal amount",
        "principal amount",
        "amount",
        "issue size",
    ),
    "coupon": (
        "coupon",
        "interest rate",
        "rate of interest",
        "rate(s) of interest",
        "interest basis",
    ),
    "issue_date": ("issue date", "settlement date", "closing date", "original issue date"),
    "maturity": ("maturity date", "maturity"),
    "format": ("format", "offering format", "selling restrictions", "regulation"),
    "listing": (
        "listing",
        "exchange",
        "admission to trading",
        "listing and admission to trading",
    ),
    "governing_law": ("governing law", "law", "applicable law", "applicable law"),
}

# Labels of the other languages (German, French, Spanish, Italian, Dutch) are merged into the
# table above, so the same rules read a term sheet in any of them. See languages.py.
for _pack in LABELS.values():
    for _key, _names in _pack.items():
        _LABELS[_key] = tuple(dict.fromkeys((*_LABELS.setdefault(_key, ()), *_names)))

# "3.", "(iv)", "4.1" or "A)" at the start of a label is a row number, not part of the name.
_ROW_NUMBER = re.compile(r"^(?:\(?[0-9]+(?:\.[0-9]+)*[.)]?|\(?[ivx]+\)|[a-z]\))\s+", re.I)


def parse_date(value: str) -> date | None:
    """Dates such as 2032-11-13, 13/11/2032, 13.11.2032, "13 November 2032", "13. November 2032",
    "13 janvier 2032" or "13 de enero de 2032" (month names of every supported language)."""
    value = value.strip().rstrip(".")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # Search, not match: "Interest Payment Date falling on or nearest to 13 November 2032" holds
    # the date. "1er", "13.", "13th" and the "de" of Spanish/Italian dates are skipped.
    match = re.search(
        r"(\d{1,2})(?:st|nd|rd|th|er|\.|º)?\s+(?:de\s+|di\s+|d')?([^\W\d_]+)\.?\s+(?:de\s+|del\s+)?(\d{4})",
        value,
        re.I,
    )
    if match:
        month = month_number(match.group(2))
        if month:
            try:
                return date(int(match.group(3)), month, int(match.group(1)))
            except ValueError:
                return None
    return None


_UNIT_MILLION = (
    "million",
    "millionen",
    "millón",
    "millones",
    "milioni",
    "miljoen",
    "mm",
    "m",
    "mio",
    "mio.",
)
_UNIT_BILLION = ("billion", "milliard", "milliarde", "milliards", "bn", "mrd", "mrd.")


def parse_size_mm(value: str) -> float | None:
    """'EUR 750,000,000', 'EUR 750m', '750 Millionen' and 'EUR 500.000.000' all become millions."""
    # Digits may be grouped with spaces too ("750 000 000", French style).
    match = re.search(
        r"(\d{1,3}(?:[ \u00a0]\d{3})+(?:[.,]\d+)?|\d[\d.,]*)\s*([A-Za-zéóÉ.]+)?", value
    )
    if not match:
        return None
    number = to_float(match.group(1).rstrip(".,"))
    if number is None:
        return None
    unit = (match.group(2) or "").lower()
    if unit in _UNIT_BILLION:
        return number * 1000
    if unit in _UNIT_MILLION:
        return number
    return number / 1_000_000 if number >= 1_000_000 else number


# What a real amount looks like: a currency code next to digits, a unit, or a long grouped number.
_AMOUNT = re.compile(
    r"\b[A-Z]{3}\s*\d|\d\s*(?:million|millionen|millón|millones|milioni|miljoen|mm|m|mio\.?|billion|milliard|milliarde|bn|mrd\.?)\b|\d{1,3}(?:[.,\s ]\d{3}){2,}",
    re.IGNORECASE,
)

# Currency names that appear instead of a code in some Final Terms ("Euro (\u201cEUR\u201d)").
_CURRENCY_NAMES = CURRENCY_NAMES


def looks_like_amount(value: str) -> bool:
    """True when `value` can be an amount of money, so "1" or "(Condition 1)" is not read as 1m."""
    return bool(_AMOUNT.search(value))


def parse_currency(value: str) -> str | None:
    """A 3-letter code, preferably the one in brackets, or a known currency name."""
    bracketed = re.search(r"\(\W{0,3}([A-Z]{3})\W{0,3}\)", value)
    if bracketed:
        return bracketed.group(1)
    code = re.search(r"\b[A-Z]{3}\b", value.upper())
    if code and code.group(0) not in {"THE", "AND", "PER"}:
        return code.group(0)
    lowered = value.lower()
    return next((iso for name, iso in _CURRENCY_NAMES.items() if name in lowered), None)


# The title of every Final Terms: "Issue of EUR 500,000,000 3.750 per cent. Senior Notes due
# 25 January 2028 ... by <issuer> (the "Bank")". It is the most reliable place for the key terms.
_HEADLINE = re.compile(
    # "Issue of EUR 1,500,000,000 4.750% Fixed to Floating Rate Senior Non Preferred Notes due ..."
    # The coupon may be "3.750 per cent." or "4.750%", up to 70 characters of note description may
    # follow, and the maturity may be a full date or only "November 2032" (then it stays empty).
    r"Issue\s+of\s+([A-Z]{3})\s*([\d.,]+\d)\s*(?:([\d.,]+)\s*(?:per\s*cent\.?|%))?"
    r"[A-Za-z\s-]{0,70}?Notes?\s+due\s+(?:(\d{1,2}\s+[A-Za-z]+\s+\d{4})|[A-Za-z]+\s+\d{4})?",
    re.IGNORECASE,
)
_HEADLINE_ISSUER = re.compile(
    r"\bby\s+(?:the\s+)?(?:\S+\s+Branch\s+of\s+)?([A-Z][^()\n]{2,80}?)\s*\(\s*the\s", re.DOTALL
)


# Some issuers print a cover line without "Issue of": "EUR 15,000,000 3.375 per cent. Senior
# Preferred Notes due 2036". It gives currency, size and coupon; a bare year is not a maturity date.
_COVER_LINE = re.compile(
    r"^\s*([A-Z]{3})\s*([\d.,]{5,})\s+([\d.,]+)\s*(?:per\s*cent\.?|%)\s+[A-Za-z ]{0,70}?Notes?\s+due\b",
    re.MULTILINE,
)

_ISIN_SHAPE = re.compile(r"\b[A-Z]{2}[A-Z0-9]{9}\d\b")
_LAW = re.compile(
    r"\b(English|German|French|Italian|Spanish|Dutch|Swiss|Luxembourg|New York)\s+law\b", re.I
)
# The same statement in the other languages: "deutschem Recht", "droit français", "derecho español".
_LAW_OTHER = re.compile(
    r"\b(?:(?:deutsch|englisch|schweizer)\w*\s+recht|droit\s+(?:fran[cç]ais|anglais|allemand|luxembourgeois)"
    r"|derecho\s+(?:espa[nñ]ol|ingl[eé]s|alem[aá]n)|diritto\s+(?:italiano|inglese|tedesco)"
    r"|(?:nederlands|engels|duits)\s+recht)\b",
    re.I,
)
_LAW_OTHER_CONTEXT = re.compile(
    r"unterlieg|recht\s+der|soumis|gouvern|r[eé]gi|rige|sujet|regol|disciplin|beheerst|onderworpen",
    re.I,
)
# Words that make a mention of a law a statement of the governing law, not just a reference.
_LAW_CONTEXT = re.compile(r"governed|governing|applicable|subject\s+to|laws?\s+of", re.I)


def scan_isin(text: str) -> str | None:
    """Find the deal's ISIN anywhere in the text, whatever the layout or language.

    Every candidate must pass the ISIN check digit, which removes look-alikes such as part numbers.
    A candidate right after the word "ISIN" wins; otherwise the most repeated one does.
    """
    candidates = [m for m in _ISIN_SHAPE.finditer(text) if is_valid_isin(m.group(0))]
    if not candidates:
        return None
    for m in candidates:
        if "isin" in text[max(0, m.start() - 20) : m.start()].lower():
            return m.group(0)
    counts: dict[str, int] = {}
    for m in candidates:
        counts[m.group(0)] = counts.get(m.group(0), 0) + 1
    return max(counts, key=lambda isin: counts[isin])  # ties keep the first one found


def scan_governing_law(text: str) -> str | None:
    """ "German law" from a sentence such as "...governed by German law", when no row states it."""
    for m in _LAW.finditer(text):
        if _LAW_CONTEXT.search(text[max(0, m.start() - 80) : m.end()]):
            return f"{m.group(1).title()} law"
    for m in _LAW_OTHER.finditer(text):
        if _LAW_OTHER_CONTEXT.search(text[max(0, m.start() - 120) : m.end() + 40]):
            return m.group(0).strip().capitalize()
    return None


def _headline(text: str) -> TermSheetRecord:
    """Key terms from the "Issue of ... Notes due ..." title; all fields stay None without one."""
    match = _HEADLINE.search(text)
    if not match:
        cover = _COVER_LINE.search(text)
        if cover:
            amount = to_float(cover.group(2)) or 0.0
            return TermSheetRecord(
                currency=cover.group(1).upper(),
                size_mm=amount / 1_000_000 if amount >= 1_000_000 else amount,
                coupon_pct=to_float(cover.group(3)),
            )
        return TermSheetRecord()
    amount = to_float(match.group(2)) or 0.0
    issuer = _HEADLINE_ISSUER.search(text[match.end() :])
    return TermSheetRecord(
        currency=match.group(1).upper(),
        size_mm=amount / 1_000_000 if amount >= 1_000_000 else amount,
        coupon_pct=to_float(match.group(3)) if match.group(3) else None,
        maturity=parse_date(match.group(4)) if match.group(4) else None,
        issuer=" ".join(issuer.group(1).split()) if issuer else None,
    )


# "per cent", "%", and the same words in the other languages ("Prozent", "pour cent", "por ciento").
_PERCENT = r"(?:%|per\s*cent\.?|prozent|pour\s*cent|por\s*ciento|per\s*cento|procent)"


def parse_coupon(value: str) -> float | None:
    """Read "3.375%", "3,375 %" or "3.750 per cent. per annum" as a percentage number."""
    match = re.search(rf"(\d+(?:[.,]\d+)?)\s*{_PERCENT}", value, re.IGNORECASE)
    return to_float(match.group(1)) if match else None


def normalise_format(value: str) -> str:
    lowered = value.lower()
    if "144a" in lowered:
        return "144A"
    if "reg s" in lowered or "regulation s" in lowered:
        return "Reg S"
    if "domestic" in lowered:
        return "Domestic"
    return value.strip()


# "(Condition 4)" and "(Conditions 4 and 5)" point to the legal conditions; they are not values.
_CONDITION_REF = re.compile(r"\(\s*Conditions?\s+[0-9][^)]*\)", re.I)

# A numbered row such as "4. Issue Price" starts a new term, so it ends the search for a value.
_NEW_ROW = re.compile(r"^\(?[0-9]+[.)]\s")

# A sub-row such as "(i) Series: EUR 500,000,000": its value belongs to the label above it.
# Some documents drop the numeral and print just "Series: EUR ..." / "Tranche: EUR ...".
_SUB_ROW = re.compile(
    r"^(?:\(?[ivx]+\)\s+[A-Za-z][A-Za-z /-]{1,40}|(?:Series|Tranche)):\s*(\S.*)$", re.I
)

# Text that is a label row ("Issue Price: 99.5") and therefore not the value we look for.
_LABEL_ROW = re.compile(r"^[^:]{1,60}:\s")


def _value_for_empty_label(lines: list[str], index: int) -> str:
    """Find the value of a label whose own line has none (typical for PDF tables).

    PDF tables are flattened to text in odd orders, so two places are tried:
    1. the next few lines (skipping references and taking the first "(i) Series: ..." sub-row),
    2. the line just before the label, where some tables print the value above its label.
    """
    for follower in lines[index + 1 : index + 5]:
        text = _CONDITION_REF.sub("", follower).strip()
        if not text:
            continue
        sub = _SUB_ROW.match(text)
        if sub:
            return sub.group(1).strip()
        if _NEW_ROW.match(text) or _LABEL_ROW.match(text):
            break  # the next term began; there is no value after the label
        return text
    for earlier in reversed(lines[max(0, index - 2) : index]):
        text = _CONDITION_REF.sub("", earlier).strip()
        if not text:
            continue
        if _NEW_ROW.match(text) or _LABEL_ROW.match(text) or len(text) > 80:
            break
        return text
    return ""


def _labelled_values(text: str) -> dict[str, str]:
    """Read "Label: value" rows into {field: value}. The first match for a field wins."""
    found: dict[str, str] = {}
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = re.sub(r"^[\s\-*#|]+", "", label).strip().lower()
        # Drop row numbers ("6. (i) Issue Date" has two) and a trailing note in brackets.
        previous = None
        while previous != label:
            previous = label
            label = _ROW_NUMBER.sub("", label)
        label = re.sub(r"\s*\([^)]*\)\s*$", "", label).strip()
        value = _CONDITION_REF.sub("", value).strip().strip("|").strip()
        if not value:
            value = _value_for_empty_label(lines, index)
            if not value:
                continue
        for key, names in _LABELS.items():
            if key not in found and label in names:
                found[key] = value
    return found


def extract_with_rules(text: str) -> TermSheetRecord:
    """Read the key terms with fixed rules: the title first, then "Label: value" rows."""
    values = _labelled_values(text)
    head = _headline(text)
    isin = None
    if "isin" in values:
        match = re.search(r"[A-Z]{2}[A-Z0-9]{9}\d", values["isin"].upper())
        isin = match.group(0) if match else values["isin"].strip().upper()
    if not isin or not is_valid_isin(isin):
        # No usable "ISIN:" row (the label may have no colon, or sit in a table): look anywhere.
        isin = scan_isin(text) or isin

    # Currency and size: the title wins when present, then the labelled rows. An amount row
    # that does not look like money is ignored, so a stray number never becomes the deal size.
    currency = head.currency or (
        parse_currency(values["currency"]) if "currency" in values else None
    )
    size_text = values.get("size", "")
    size = head.size_mm or (
        parse_size_mm(size_text) if size_text and looks_like_amount(size_text) else None
    )
    if currency is None and size_text:
        match = re.search(r"\b(EUR|USD|GBP|CHF)\b", size_text.upper())
        currency = match.group(1) if match else None

    coupon = head.coupon_pct or (parse_coupon(values["coupon"]) if "coupon" in values else None)
    maturity = head.maturity or (parse_date(values["maturity"]) if "maturity" in values else None)
    return TermSheetRecord(
        issuer=values.get("issuer") or head.issuer,
        isin=isin,
        currency=currency,
        size_mm=size,
        coupon_pct=coupon,
        issue_date=parse_date(values["issue_date"]) if "issue_date" in values else None,
        maturity=maturity,
        format=normalise_format(values["format"]) if "format" in values else None,
        listing=values.get("listing"),
        governing_law=values.get("governing_law") or scan_governing_law(text),
    )
