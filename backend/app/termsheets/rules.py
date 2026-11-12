"""A rule-based extractor for "Label: value" term sheets.

It is the safety net when the model is unavailable or leaves a field empty, and it makes the
extraction testable without a GPU. It reads only simple labelled lines.
"""

import re
from datetime import date, datetime

from app.termsheets.models import TermSheetRecord

_LABELS: dict[str, tuple[str, ...]] = {
    "issuer": ("issuer", "borrower"),
    "isin": ("isin",),
    "currency": ("currency",),
    "size": ("size", "aggregate nominal amount", "principal amount", "amount", "issue size"),
    "coupon": ("coupon", "interest rate", "rate of interest"),
    "issue_date": ("issue date", "settlement date", "closing date"),
    "maturity": ("maturity date", "maturity"),
    "format": ("format", "offering format", "selling restrictions", "regulation"),
    "listing": ("listing", "exchange", "admission to trading"),
    "governing_law": ("governing law", "law"),
}

_MONTHS = {
    m: i
    for i, m in enumerate(
        [
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
        ],
        start=1,
    )
}


def parse_date(value: str) -> date | None:
    value = value.strip().rstrip(".")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    match = re.match(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)\s+(\d{4})", value)
    if match and match.group(2).lower() in _MONTHS:
        try:
            return date(int(match.group(3)), _MONTHS[match.group(2).lower()], int(match.group(1)))
        except ValueError:
            return None
    return None


def parse_size_mm(value: str) -> float | None:
    """'EUR 750,000,000', 'EUR 750m' and '750 million' all become 750.0."""
    match = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(million|mm|m|billion|bn)?\b", value, re.IGNORECASE)
    if not match:
        return None
    number = float(match.group(1).replace(",", ""))
    unit = (match.group(2) or "").lower()
    if unit in ("billion", "bn"):
        return number * 1000
    if unit in ("million", "mm", "m"):
        return number
    return number / 1_000_000 if number >= 1_000_000 else number


def parse_coupon(value: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", value)
    return float(match.group(1)) if match else None


def normalise_format(value: str) -> str:
    lowered = value.lower()
    if "144a" in lowered:
        return "144A"
    if "reg s" in lowered or "regulation s" in lowered:
        return "Reg S"
    if "domestic" in lowered:
        return "Domestic"
    return value.strip()


def _labelled_values(text: str) -> dict[str, str]:
    found: dict[str, str] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label = re.sub(r"^[\s\-*#|]+", "", label).strip().lower()
        value = value.strip().strip("|").strip()
        if not value:
            continue
        for key, names in _LABELS.items():
            if key not in found and label in names:
                found[key] = value
    return found


def extract_with_rules(text: str) -> TermSheetRecord:
    values = _labelled_values(text)
    isin = None
    if "isin" in values:
        match = re.search(r"[A-Z]{2}[A-Z0-9]{9}\d", values["isin"].upper())
        isin = match.group(0) if match else values["isin"].strip().upper()
    currency = None
    if "currency" in values:
        match = re.search(r"\b[A-Z]{3}\b", values["currency"].upper())
        currency = match.group(0) if match else None
    elif "size" in values:
        match = re.search(r"\b(EUR|USD|GBP|CHF)\b", values["size"].upper())
        currency = match.group(1) if match else None
    return TermSheetRecord(
        issuer=values.get("issuer"),
        isin=isin,
        currency=currency,
        size_mm=parse_size_mm(values["size"]) if "size" in values else None,
        coupon_pct=parse_coupon(values["coupon"]) if "coupon" in values else None,
        issue_date=parse_date(values["issue_date"]) if "issue_date" in values else None,
        maturity=parse_date(values["maturity"]) if "maturity" in values else None,
        format=normalise_format(values["format"]) if "format" in values else None,
        listing=values.get("listing"),
        governing_law=values.get("governing_law"),
    )
