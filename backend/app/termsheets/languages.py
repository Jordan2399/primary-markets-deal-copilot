"""Language packs for the fixed rules: labels, month names and number formats per language.

The rules stay the same for every language; only the vocabulary changes. A language is a plain
data entry, so adding Portuguese or Swedish means adding one dict, not new code. Anything the
packs do not cover (another language, an unusual layout) still reaches the model, which reads
many languages; the rules just make the common ones fast and exact.
"""

import re

# Label spellings per field, per language. Keys match `_LABELS` in rules.py.
LABELS: dict[str, dict[str, tuple[str, ...]]] = {
    "de": {
        "issuer": ("emittentin", "emittent"),
        "isin": ("isin", "wertpapierkennnummer"),
        "currency": ("währung", "festgelegte währung", "emissionswährung"),
        "size": ("gesamtnennbetrag", "nennbetrag", "emissionsvolumen"),
        "coupon": ("zinssatz", "verzinsung", "kupon"),
        "issue_date": ("begebungstag", "valutatag", "emissionstag"),
        "maturity": ("fälligkeitstag", "endfälligkeitstag", "rückzahlungstag", "laufzeitende"),
        "listing": ("börsenzulassung", "börsennotierung", "zulassung zum handel"),
        "governing_law": ("anwendbares recht", "maßgebliches recht"),
    },
    "fr": {
        "issuer": ("émetteur",),
        "currency": ("devise", "devise de l'émission", "devise prévue"),
        "size": ("montant nominal total", "montant nominal", "montant de l'émission"),
        "coupon": ("taux d'intérêt", "taux de l'intérêt", "coupon"),
        "issue_date": ("date d'émission", "date de règlement"),
        "maturity": ("date d'échéance", "échéance", "date de remboursement"),
        "listing": ("cotation", "admission aux négociations", "marché"),
        "governing_law": ("droit applicable", "loi applicable"),
    },
    "es": {
        "issuer": ("emisor",),
        "currency": ("divisa", "moneda", "divisa especificada"),
        "size": ("importe nominal total", "importe nominal", "importe de la emisión"),
        "coupon": ("tipo de interés", "cupón", "tasa de interés"),
        "issue_date": ("fecha de emisión", "fecha de desembolso"),
        "maturity": ("fecha de vencimiento", "vencimiento"),
        "listing": ("cotización", "admisión a negociación"),
        "governing_law": ("ley aplicable", "legislación aplicable"),
    },
    "it": {
        "issuer": ("emittente",),
        "currency": ("valuta", "valuta specificata"),
        "size": ("importo nominale complessivo", "importo nominale", "ammontare dell'emissione"),
        "coupon": ("tasso di interesse", "cedola", "tasso d'interesse"),
        "issue_date": ("data di emissione", "data di regolamento"),
        "maturity": ("data di scadenza", "scadenza"),
        "listing": ("quotazione", "ammissione alla negoziazione"),
        "governing_law": ("legge applicabile", "diritto applicabile"),
    },
    "nl": {
        "issuer": ("uitgevende instelling", "emittent"),
        "currency": ("valuta", "gespecificeerde valuta"),
        "size": ("totale hoofdsom", "nominaal bedrag", "totaal nominaal bedrag"),
        "coupon": ("rentevoet", "couponrente", "rente"),
        "issue_date": ("uitgiftedatum", "datum van uitgifte"),
        "maturity": ("einddatum", "vervaldatum", "aflossingsdatum"),
        "listing": ("notering", "toelating tot de handel"),
        "governing_law": ("toepasselijk recht",),
    },
}

# Month names (lower case, accents kept) per language; "may" is in English only to be safe.
MONTHS: dict[str, tuple[str, ...]] = {
    "en": (
        "january",
        "february",
        "march",
        "april",
        "may",
        "june",
        "july",
        "august",
        "september",
        "october",
        "november",
        "december",
    ),
    "de": (
        "januar",
        "februar",
        "märz",
        "april",
        "mai",
        "juni",
        "juli",
        "august",
        "september",
        "oktober",
        "november",
        "dezember",
    ),
    "fr": (
        "janvier",
        "février",
        "mars",
        "avril",
        "mai",
        "juin",
        "juillet",
        "août",
        "septembre",
        "octobre",
        "novembre",
        "décembre",
    ),
    "es": (
        "enero",
        "febrero",
        "marzo",
        "abril",
        "mayo",
        "junio",
        "julio",
        "agosto",
        "septiembre",
        "octubre",
        "noviembre",
        "diciembre",
    ),
    "it": (
        "gennaio",
        "febbraio",
        "marzo",
        "aprile",
        "maggio",
        "giugno",
        "luglio",
        "agosto",
        "settembre",
        "ottobre",
        "novembre",
        "dicembre",
    ),
    "nl": (
        "januari",
        "februari",
        "maart",
        "april",
        "mei",
        "juni",
        "juli",
        "augustus",
        "september",
        "oktober",
        "november",
        "december",
    ),
}

# Common spelling variants that are not the plain month name.
MONTH_ALIASES: dict[str, int] = {"marz": 3, "sept": 9, "septembre": 9, "setiembre": 9, "janner": 1}

# Currency names by language that stand in for a code.
CURRENCY_NAMES: dict[str, str] = {
    "euro": "EUR",
    "us dollar": "USD",
    "u.s. dollar": "USD",
    "us-dollar": "USD",
    "dollar américain": "USD",
    "dólar estadounidense": "USD",
    "dollaro statunitense": "USD",
    "pound sterling": "GBP",
    "pfund sterling": "GBP",
    "livre sterling": "GBP",
    "libra esterlina": "GBP",
    "sterlina": "GBP",
    "swiss franc": "CHF",
    "schweizer franken": "CHF",
    "franc suisse": "CHF",
    "franco suizo": "CHF",
    "franco svizzero": "CHF",
    "zwitserse frank": "CHF",
}

# Words that tell the languages apart. A few frequent function words are enough to pick one.
_MARKERS: dict[str, tuple[str, ...]] = {
    "en": ("the", "of", "and", "notes", "issuer", "governed", "shall", "date"),
    "de": ("der", "die", "das", "und", "emittentin", "schuldverschreibungen", "gemäß", "recht"),
    "fr": ("le", "la", "les", "et", "émetteur", "obligations", "droit", "conformément"),
    "es": ("el", "los", "y", "emisor", "obligaciones", "derecho", "conforme", "importe"),
    "it": ("il", "gli", "e", "emittente", "obbligazioni", "diritto", "conformemente", "importo"),
    "nl": ("de", "het", "en", "obligaties", "uitgevende", "recht", "bedrag", "volgens"),
}


def detect_language(text: str) -> str:
    """Best guess of the main language as a code ("en", "de", "fr", "es", "it", "nl").

    Counts marker words in the first 20,000 characters. Returns "en" when nothing stands out.
    """
    words = re.findall(r"[a-zäöüßéèêàçíóúñ']+", text[:20_000].lower())
    if not words:
        return "en"
    counts: dict[str, int] = {}
    for word in words:
        counts[word] = counts.get(word, 0) + 1
    scores = {lang: sum(counts.get(m, 0) for m in markers) for lang, markers in _MARKERS.items()}
    best = max(scores, key=lambda lang: scores[lang])
    return best if scores[best] >= 3 else "en"


def month_number(name: str) -> int | None:
    """1-12 for a month name in any supported language, else None."""
    lowered = name.lower().rstrip(".")
    if lowered in MONTH_ALIASES:
        return MONTH_ALIASES[lowered]
    for names in MONTHS.values():
        if lowered in names:
            return names.index(lowered) + 1
    return None


def to_float(number: str) -> float | None:
    """Parse "1,500,000,000", "1.500.000.000", "3,750" and "3.750" into a float.

    The last separator is the decimal point only when 1-2 digits follow it, or when it differs
    from the separator used for the groups and 3 digits follow with no other group separator.
    Examples: "3,750" -> 3.75 (a coupon), "500.000.000" -> 500000000.0, "1,500.5" -> 1500.5.
    """
    s = number.strip().replace(" ", "").replace(" ", "").replace("'", "")
    if not re.fullmatch(r"\d[\d.,]*", s):
        return None
    commas, dots = s.count(","), s.count(".")
    if commas and dots:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
    elif commas or dots:
        sep = "," if commas else "."
        parts = s.split(sep)
        # A single separator followed by exactly 3 digits and a group of 1-3 digits before it
        # is ambiguous: "500,000" is a grouped amount, "3,750" a coupon. Several separators or a
        # leading part of 4+ digits can only be grouping.
        if len(parts) > 2:
            decimal = None
        elif len(parts[1]) == 3 and len(parts[0]) >= 3:
            decimal = None  # "500,000" / "500.000": grouped
        else:
            decimal = sep
    else:
        decimal = None
    if decimal is None:
        return float(re.sub(r"[.,]", "", s))
    other = "." if decimal == "," else ","
    return float(s.replace(other, "").replace(decimal, "."))
