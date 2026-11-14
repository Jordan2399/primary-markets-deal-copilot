"""Long-PDF handling: cleaning, the terms-section finder, numbered labels and the one-source rule.

The PDFs are generated here with reportlab in the layout of real Final Terms: a running header,
a footer with page numbers, numbered rows, a value that wraps onto the next line, and filler legal
text. No real document is used.
"""

import io
import json

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.llm.fake import FakeLLM
from app.termsheets.cleaning import FOCUS_THRESHOLD, clean_pages, focus_terms, join_wrapped_lines
from app.termsheets.parser import read_text
from app.termsheets.rules import extract_with_rules
from tests.conftest import build_env

FILLER = (
    "The Notes are issued subject to the Terms and Conditions set out in the Base Prospectus. "
    "Investors should read this document together with the Base Prospectus and any supplement. "
)

TERMS = [
    "1. Issuer: Example Bank plc, acting through its London Branch",
    "2. ISIN: XS2579324869",
    "3. Specified Currency: Euro (EUR)",
    "4. Aggregate Nominal Amount of Notes:",
    "EUR 500,000,000",
    "5. Rate of Interest: 3.750 per cent. per annum",
    "6. Issue Date: 25 January 2023",
    "7. Maturity Date: 25 January 2028",
    "8. Listing and admission to trading: Luxembourg Stock Exchange",
    "9. Governing law: English law",
]


def make_pdf(pages: int = 12) -> bytes:
    """A multi-page PDF: terms on page 3, filler elsewhere, header and footer on every page."""
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    for number in range(1, pages + 1):
        pdf.setFont("Helvetica", 8)
        pdf.drawString(50, 810, "FINAL TERMS dated 20 January 2023")  # running header
        pdf.drawString(50, 30, f"Example Bank plc - Page {number}")  # footer with page number
        pdf.setFont("Helvetica", 10)
        y = 780
        if number == 3:
            for line in TERMS:
                pdf.drawString(50, y, line)
                y -= 16
        for _ in range(30):
            pdf.drawString(50, y, FILLER[:95])
            y -= 14
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


# ------------------------------------------------------------------ cleaning


WORDS = ["", "alpha", "beta", "gamma", "delta", "epsilon", "zeta"]


def test_headers_footers_and_page_numbers_are_removed() -> None:
    body = "\n".join(f"Paragraph {i} of the document." for i in range(8))
    pages = [
        f"HEADER LINE\nSection {WORDS[n]} begins here\n{body}\nExample Bank - Page {n}\n{n}"
        for n in range(1, 7)
    ]
    cleaned = clean_pages(pages)
    assert "HEADER LINE" not in cleaned and "Example Bank - Page" not in cleaned
    assert "Section delta begins here" in cleaned


def test_two_page_documents_keep_their_first_lines() -> None:
    cleaned = clean_pages(["Title\nIssuer: A", "Title\nCoupon: 3%"])
    assert cleaned.count("Title") == 2  # with fewer than 3 pages nothing counts as repeated


def test_hyphenated_and_wrapped_lines_are_joined_but_rows_stay_apart() -> None:
    text = "The Aggre-\ngate amount is paid\nin full.\nIssuer: Example\nCoupon: 3.75%"
    out = join_wrapped_lines(text)
    assert "Aggregate amount is paid in full." in out
    assert "\nIssuer: Example\nCoupon: 3.75%" in out


def test_isin_and_numbers_with_hyphens_are_not_damaged() -> None:
    assert "5-year" in join_wrapped_lines("a 5-year\nnote")
    assert "XS2579324869" in join_wrapped_lines("ISIN: XS2579324869")


# ------------------------------------------------------------------ real-layout PDF


def test_pdf_is_read_cleaned_and_terms_are_found_by_the_rules() -> None:
    text = read_text("final-terms.pdf", make_pdf())
    assert "Page 7" not in text and "FINAL TERMS dated" not in text
    record = extract_with_rules(text)
    assert record.isin == "XS2579324869"
    assert record.currency == "EUR"
    assert record.size_mm == 500.0  # value was on the line after the label
    assert record.coupon_pct == 3.75
    assert record.maturity is not None and record.maturity.year == 2028
    assert record.issuer and record.issuer.startswith("Example Bank")


def test_focus_keeps_the_terms_and_drops_filler() -> None:
    text = read_text("final-terms.pdf", make_pdf(pages=20))
    assert len(text) > FOCUS_THRESHOLD
    focused, shortened = focus_terms(text)
    assert shortened and len(focused) < len(text) / 2
    for needle in ("XS2579324869", "500,000,000", "3.750"):
        assert needle in focused


def test_short_documents_are_not_focused() -> None:
    focused, shortened = focus_terms("Issuer: A\nCoupon: 3%")
    assert focused == "Issuer: A\nCoupon: 3%" and not shortened


# ------------------------------------------------------------------ API


def test_file_extraction_works_without_a_model_and_reports_what_was_read() -> None:
    env = build_env(FakeLLM(fail=True))
    response = env.client.post(
        "/api/v1/documents/extract",
        files={"file": ("final-terms.pdf", make_pdf(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source"] == "file" and body["method"] == "rules"
    assert body["not_found"] == []
    assert body["record"]["isin"] == "XS2579324869"


def test_model_receives_only_the_focused_text() -> None:
    answer = json.dumps({"issuer": "Example Bank plc", "currency": "EUR"})
    fake = FakeLLM(chat_responses=[answer])
    env = build_env(fake)
    body = env.client.post(
        "/api/v1/documents/extract",
        files={"file": ("final-terms.pdf", make_pdf(pages=20), "application/pdf")},
    ).json()
    assert body["focused"] is True
    assert 0 < body["model_chars"] < body["text_chars"] / 2


def test_missing_fields_are_named() -> None:
    env = build_env(FakeLLM(fail=True))
    body = env.client.post(
        "/api/v1/documents/extract", data={"text": "Issuer: Example Bank plc\nCurrency: EUR"}
    ).json()
    assert body["source"] == "text"
    assert set(body["not_found"]) == {"isin", "size_mm", "coupon_pct", "maturity"}


def test_file_and_text_together_are_refused() -> None:
    env = build_env(FakeLLM(fail=True))
    response = env.client.post(
        "/api/v1/documents/extract",
        data={"text": "Issuer: A"},
        files={"file": ("a.txt", b"Issuer: B", "text/plain")},
    )
    assert response.status_code == 400
    assert "not both" in response.json()["error"]["message"].lower()


# ------------------------------------------------------------------ table layout of real Final Terms

# The structure of a real Final Terms page as a PDF reader flattens it: a title sentence with the
# key terms, then a two-column table where some values come BEFORE their label, some labels have
# no value on their line, and "(Condition n)" references are scattered between rows. The names
# are invented; only the layout is real.
FLATTENED_TABLE = """\
Final Terms dated 23 January 2023 (A bank governed by the Example Act)
(LEI: 123456789012345678AB) Issue of EUR 500,000,000 3.750 per cent. Senior Notes due 25 January 2028
(the "Notes") under a US$10,000,000,000 Euro Note Programme by the London Branch of Example Bank plc
(the "Bank")
PART A - CONTRACTUAL TERMS
1. (i) Series Number: 2023-6 (Condition 1)
(ii) Tranche Number: 1
(Condition 1)
(iii) Date on which the Notes Not Applicable will be consolidated and form a single Series:
(Condition 1) Euro ("EUR")
2. Specified Currency or Currencies:
(Condition 1)
3. Aggregate Nominal Amount:
(Condition 1)
(i) Series: EUR 500,000,000
(ii) Tranche: EUR 500,000,000
4. Issue Price: 99.517 per cent. of the Aggregate Nominal Amount
(Condition 5)
5. (ii) Calculation Amount: EUR 1,000
(Condition 4)
6. (i) Issue Date: 25 January 2023 (Condition 4)
(ii) Trade Date: 18 January 2023
7. Maturity Date: 25 January 2028
(Condition 5)
8. Interest Basis: 3.750 per cent. Fixed Rate Note
(Condition 4) (further particulars specified below)
"""


def test_title_sentence_gives_amount_currency_coupon_maturity_and_issuer() -> None:
    record = extract_with_rules(FLATTENED_TABLE)
    assert record.currency == "EUR"
    assert record.size_mm == 500.0
    assert record.coupon_pct == 3.75
    assert record.maturity is not None and record.maturity.isoformat() == "2028-01-25"
    assert record.issuer == "Example Bank plc"


def test_a_condition_reference_is_never_read_as_the_size() -> None:
    # Without the title sentence only the table is left: the amount comes from the "(i) Series"
    # sub-row, and the "(Condition 1)" lines must not turn into a 1m deal.
    table_only = FLATTENED_TABLE.split("PART A - CONTRACTUAL TERMS")[1]
    record = extract_with_rules(table_only)
    assert record.size_mm == 500.0
    assert record.currency == "EUR"  # the value printed ABOVE its label
    assert record.coupon_pct == 3.75  # "Interest Basis: 3.750 per cent. Fixed Rate Note"
    assert record.issue_date is not None and record.issue_date.isoformat() == "2023-01-25"
    assert record.maturity is not None and record.maturity.isoformat() == "2028-01-25"


def test_a_lone_number_is_not_an_amount() -> None:
    assert extract_with_rules("Aggregate Nominal Amount: (Condition 1)").size_mm is None
    assert extract_with_rules("Amount: 3").size_mm is None
    assert extract_with_rules("Size: EUR 750m").size_mm == 750.0


def test_model_failure_is_reported_with_its_reason() -> None:
    env = build_env(FakeLLM(fail=True))
    body = env.client.post("/api/v1/documents/extract", data={"text": FLATTENED_TABLE}).json()
    assert body["method"] == "rules"
    assert body["model_error"] and "LLM" in body["model_error"]
    assert body["not_found"] == ["isin"]  # everything else was found by the rules


# ------------------------------------------------------------------ rules first, model for gaps
import asyncio  # noqa: E402

from app.audit.service import AuditService  # noqa: E402
from app.core.security import CurrentUser, Role  # noqa: E402
from app.deals.service import DealService  # noqa: E402
from app.termsheets.cleaning import GAP_MAX_CHARS, focus_fields  # noqa: E402
from app.termsheets.service import TermSheetService  # noqa: E402
from tests.fakes import (  # noqa: E402
    FakeAuditRepository,
    FakeDealRepository,
    FakeTermSheetRepository,
)


def _service(llm: FakeLLM, mode: str) -> TermSheetService:
    deals = FakeDealRepository()
    return TermSheetService(
        FakeTermSheetRepository(deals.events),
        DealService(deals),
        llm,
        AuditService(FakeAuditRepository(deals.events)),
        model_mode=mode,
    )


def _extract(service: TermSheetService, text: str):  # type: ignore[no-untyped-def]
    user = CurrentUser(name="Test", role=Role.syndicate)
    return asyncio.run(
        service.extract(filename=None, content=None, text=text, deal_id=None, user=user)
    )


COMPLETE = FLATTENED_TABLE + "ISIN: XS2579324869\n"


def test_gaps_mode_skips_the_model_when_the_rules_found_everything() -> None:
    llm = FakeLLM()
    out = _extract(_service(llm, "gaps"), COMPLETE)
    assert out.model_skipped and out.method == "rules" and out.model is None
    assert llm.chat_calls == []  # no model call at all
    assert out.not_found == []


def test_gaps_mode_asks_the_model_only_for_the_missing_field() -> None:
    llm = FakeLLM(chat_responses=[json.dumps({"isin": "XS2579324869", "issuer": "Wrong Bank"})])
    out = _extract(_service(llm, "gaps"), FLATTENED_TABLE)  # no ISIN in the text
    assert out.record.isin == "XS2579324869"
    assert out.filled_by_model == ["isin"] and out.method == "rules+llm"
    assert out.record.issuer == "Example Bank plc"  # the rules' value is kept over the model's
    assert len(llm.chat_calls[0][1]["content"]) < GAP_MAX_CHARS + 100


def test_always_mode_keeps_the_old_behaviour() -> None:
    llm = FakeLLM(chat_responses=[json.dumps({"issuer": "Model Bank"})])
    out = _extract(_service(llm, "always"), COMPLETE)
    assert out.method == "llm+rules" and out.record.issuer == "Model Bank"


def test_focus_fields_reads_only_the_passages_of_the_missing_fields() -> None:
    filler = "Nothing relevant here at all. " * 400
    text = filler + "\nISIN: XS2579324869\n" + filler
    excerpt = focus_fields(text, ["isin"])
    assert "XS2579324869" in excerpt and len(excerpt) <= GAP_MAX_CHARS
    assert len(excerpt) < len(text) / 4
