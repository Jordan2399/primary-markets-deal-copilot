"""Validation in code. The model never decides whether a term sheet is right."""

import re
from datetime import date

from app.common.isin import is_valid_isin
from app.deals.models import DealDetail
from app.termsheets.models import (
    ALLOWED_CURRENCIES,
    ALLOWED_FORMATS,
    Check,
    DiffRow,
    TermSheetRecord,
)

REQUIRED = ("issuer", "isin", "currency", "size_mm", "coupon_pct", "maturity")
MAX_COUPON = 15.0


def validate_record(record: TermSheetRecord, source_text: str) -> list[Check]:
    checks: list[Check] = []

    def add(field: str, rule: str, ok: bool, message: str, severity: str = "error") -> None:
        checks.append(Check(field=field, rule=rule, ok=ok, severity=severity, message=message))

    for name in REQUIRED:
        present = getattr(record, name) is not None
        add(
            name,
            "required",
            present,
            "Present." if present else f"{name} is missing from the term sheet.",
        )

    if record.isin:
        add(
            "isin",
            "format",
            bool(re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", record.isin)),
            "ISIN has the right shape."
            if re.fullmatch(r"[A-Z]{2}[A-Z0-9]{9}\d", record.isin)
            else f"{record.isin} is not 12 characters in ISIN format.",
        )
        valid = is_valid_isin(record.isin)
        add(
            "isin",
            "checksum",
            valid,
            "Check digit is correct." if valid else f"{record.isin} fails the ISIN check digit.",
        )
        in_text = record.isin in source_text.upper().replace(" ", "")
        add(
            "isin",
            "in_document",
            in_text,
            "The ISIN appears in the document."
            if in_text
            else "The extracted ISIN does not appear in the document text.",
            "warning",
        )

    if record.currency:
        ok = record.currency in ALLOWED_CURRENCIES
        add(
            "currency",
            "allowed",
            ok,
            "Currency is supported."
            if ok
            else f"{record.currency} is not one of {', '.join(ALLOWED_CURRENCIES)}.",
        )

    if record.size_mm is not None:
        ok = 50 <= record.size_mm <= 5000
        add(
            "size_mm",
            "range",
            ok,
            "Size is in the usual range."
            if ok
            else f"Size {record.size_mm:g}m is outside 50m to 5,000m.",
        )

    if record.coupon_pct is not None:
        ok = 0 <= record.coupon_pct <= MAX_COUPON
        add(
            "coupon_pct",
            "range",
            ok,
            "Coupon is in a sane range."
            if ok
            else f"Coupon {record.coupon_pct}% is outside 0% to {MAX_COUPON:g}%.",
        )

    if record.maturity and record.issue_date:
        ok = record.maturity > record.issue_date
        add(
            "maturity",
            "after_issue",
            ok,
            "Maturity is after the issue date." if ok else "Maturity is not after the issue date.",
        )
    elif record.maturity and not record.issue_date:
        add(
            "maturity",
            "after_issue",
            False,
            "No issue date, so maturity could not be checked.",
            "warning",
        )

    if record.format:
        ok = record.format in ALLOWED_FORMATS
        add(
            "format",
            "allowed",
            ok,
            "Format is recognised."
            if ok
            else f"'{record.format}' is not one of {', '.join(ALLOWED_FORMATS)}.",
            "warning",
        )
    return checks


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _fmt(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def diff_with_booking(record: TermSheetRecord, deal: DealDetail) -> list[DiffRow]:
    tranche = deal.tranches[0] if deal.tranches else None
    pairs: list[tuple[str, object, object, str]] = [
        ("issuer", record.issuer, deal.issuer_name, "name"),
        ("isin", record.isin, tranche.isin if tranche else None, "exact"),
        ("currency", record.currency, deal.currency, "exact"),
        ("size_mm", record.size_mm, float(deal.size_mm), "number"),
        ("coupon_pct", record.coupon_pct, tranche.coupon if tranche else None, "coupon"),
        ("maturity", record.maturity, tranche.maturity if tranche else None, "exact"),
        ("format", record.format, tranche.format if tranche else None, "exact"),
    ]
    rows: list[DiffRow] = []
    for field, sheet, booked, mode in pairs:
        if sheet is None and booked is None:
            status = "match"
        elif sheet is None:
            status = "missing_in_term_sheet"
        elif booked is None:
            status = "missing_in_booking"
        elif mode == "name":
            status = "match" if _norm_name(str(sheet)) == _norm_name(str(booked)) else "mismatch"
        elif mode == "number":
            status = "match" if abs(float(sheet) - float(booked)) < 0.0005 else "mismatch"  # type: ignore[arg-type]
        elif mode == "coupon":
            status = "match" if abs(float(sheet) - float(booked)) < 0.0005 else "mismatch"  # type: ignore[arg-type]
        else:
            status = "match" if sheet == booked else "mismatch"
        rows.append(
            DiffRow(field=field, term_sheet=_fmt(sheet), booking=_fmt(booked), status=status)
        )
    return rows
