"""Term sheet models."""

from datetime import date, datetime

from pydantic import BaseModel, Field

ALLOWED_CURRENCIES = ("EUR", "USD", "GBP", "CHF")
ALLOWED_FORMATS = ("Reg S", "144A", "Domestic")


class TermSheetRecord(BaseModel):
    """What we pull out of a term sheet. A field is None when the document does not say."""

    issuer: str | None = None
    isin: str | None = None
    currency: str | None = None
    size_mm: float | None = Field(None, description="Aggregate size in millions of the currency")
    coupon_pct: float | None = Field(None, description="Annual coupon in percent, e.g. 3.375")
    issue_date: date | None = None
    maturity: date | None = None
    format: str | None = Field(None, description="Reg S, 144A or Domestic")
    listing: str | None = None
    governing_law: str | None = None


class StoredTermSheet(BaseModel):
    id: str
    filename: str
    deal_id: str | None
    content_hash: str
    text: str
    record: TermSheetRecord
    method: str  # llm | rules | llm+rules
    model: str | None
    extracted_by: str
    extracted_at: datetime


class ExtractionOut(BaseModel):
    document_id: str
    filename: str
    deal_id: str | None
    method: str
    model: str | None
    text_chars: int
    record: TermSheetRecord
    source: str = "text"  # text or file: which input was read (never both)
    focused: bool = False  # True when only the terms passages were sent to the model
    model_chars: int = 0  # how many characters the model actually read
    not_found: list[str] = Field(default_factory=list)  # fields no reader could find
    model_error: str | None = None  # why the model gave no answer (rules were used instead)
    model_skipped: bool = False  # True when the rules found every required field
    filled_by_model: list[str] = Field(default_factory=list)  # fields only the model filled


class Check(BaseModel):
    field: str
    rule: str
    ok: bool
    severity: str  # error | warning
    message: str


class DiffRow(BaseModel):
    field: str
    term_sheet: str | None
    booking: str | None
    status: str  # match | mismatch | missing_in_term_sheet | missing_in_booking


class ValidationReport(BaseModel):
    document_id: str
    deal_id: str | None
    checks: list[Check]
    diff: list[DiffRow] | None
    has_errors: bool
    has_mismatch: bool


class SampleOut(BaseModel):
    filename: str
    text: str
    variant: str
