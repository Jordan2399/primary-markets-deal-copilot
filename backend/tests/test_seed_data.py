from datetime import date

import pytest
from pydantic import TypeAdapter

from app.common.isin import is_valid_isin
from app.deals.models import CreateDealRequest
from app.deals.templates import STAGE_BY_CODE
from app.documents.chunking import chunk_markdown
from app.seed.data import DEALS, ISSUER_BY_ID, ISSUERS, deal_name, launch_date, pricing_terms
from app.seed.runner import PLAYBOOK_DIR


def test_issuer_ids_are_unique() -> None:
    assert len({i.id for i in ISSUERS}) == len(ISSUERS) == 25


def test_deals_reference_real_issuers_and_stages() -> None:
    ids = [d.deal_id for d in DEALS]
    assert len(ids) == len(set(ids))
    for deal in DEALS:
        assert deal.issuer_id in ISSUER_BY_ID
        assert deal.stage_code in STAGE_BY_CODE


def test_deal_attributes_are_accepted_by_the_api_model() -> None:
    currency = TypeAdapter(CreateDealRequest).validate_python
    for deal in DEALS:
        currency(
            {
                "issuer_id": deal.issuer_id,
                "name": deal_name(deal),
                "currency": deal.currency,
                "size_mm": deal.size_mm,
                "tenor_years": deal.tenor_years,
                "format": deal.format,
                "launch_date": date(2027, 1, 1),
            }
        )


def test_demo_deal_is_in_documentation() -> None:
    demo = next(d for d in DEALS if d.deal_id == "D-DEMO-001")
    assert demo.stage_code == "documentation"


def test_every_stage_is_represented_in_the_pipeline() -> None:
    assert {d.stage_code for d in DEALS} == set(STAGE_BY_CODE)


def test_pricing_terms_exist_only_from_pricing_on_and_isins_are_valid() -> None:
    for deal in DEALS:
        coupon, isin = pricing_terms(deal)
        if STAGE_BY_CODE[deal.stage_code].position >= STAGE_BY_CODE["pricing"].position:
            assert coupon is not None and 2.5 <= coupon <= 4.75
            assert isin is not None and is_valid_isin(isin) and isin.startswith("XS9999")
        else:
            assert (coupon, isin) == (None, None)


def test_pricing_terms_are_deterministic_and_isins_unique() -> None:
    first = [pricing_terms(d) for d in DEALS]
    assert first == [pricing_terms(d) for d in DEALS]
    isins = [i for _, i in first if i]
    assert len(isins) == len(set(isins))


def test_launch_date_is_relative_to_today() -> None:
    demo = next(d for d in DEALS if d.deal_id == "D-DEMO-001")
    assert launch_date(demo, date(2026, 11, 3)) == date(2026, 11, 17)


def test_playbook_has_enough_pages_and_every_page_chunks() -> None:
    pages = sorted(PLAYBOOK_DIR.glob("*.md"))
    assert len(pages) >= 10
    seen: set[str] = set()
    for page in pages:
        title, chunks = chunk_markdown(f"playbook-{page.stem}", page.read_text(encoding="utf-8"))
        assert title != "Untitled", page.name
        assert len(chunks) >= 3, page.name
        for chunk in chunks:
            assert chunk.id not in seen
            seen.add(chunk.id)
            assert 0 < len(chunk.text) <= 1300


@pytest.mark.parametrize("stage", list(STAGE_BY_CODE))
def test_every_stage_has_a_playbook_page(stage: str) -> None:
    assert (PLAYBOOK_DIR / f"{stage.replace('_', '-')}.md").exists()
