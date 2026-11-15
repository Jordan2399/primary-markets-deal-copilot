"""The target score: every factor, its limits and the explanations. No database, no model."""

import pytest

from app.investors.models import Investor
from app.investors.scoring import (
    PARTICIPATION_CAP,
    POINTS_PARTICIPATION,
    POINTS_REAL_MONEY,
    POINTS_REGION_GAP,
    POINTS_TICKET_FIT,
    fmt_k,
    score_investor,
    ticket_fit,
)


def investor(**changes: object) -> Investor:
    base = dict(
        id="INV-001", name="Aldergate Capital", type="asset_manager", region="UK",
        real_money=True, esg_focus=False, ticket_mean_k=25_000, ticket_std_k=5_000,
        past_participation=20,
    )  # fmt: skip
    return Investor(**{**base, **changes})  # type: ignore[arg-type]


def test_ticket_fit_is_one_inside_the_band_and_falls_off_outside() -> None:
    assert ticket_fit(25_000, 750_000) == 1.0  # 3.3% of the deal
    assert ticket_fit(7_500, 750_000) == 1.0  # exactly 1%
    assert ticket_fit(3_750, 750_000) == pytest.approx(0.5)  # half the lower edge
    assert ticket_fit(150_000, 750_000) == pytest.approx(0.5)  # 20%: twice the upper edge
    assert ticket_fit(0, 750_000) == 0.0 and ticket_fit(1_000, 0) == 0.0


def test_a_perfect_investor_with_a_region_gap_scores_100() -> None:
    score, reasons, cautions = score_investor(
        investor(), deal_size_k=750_000, currency="EUR", region_share=0.0
    )
    assert score == POINTS_REAL_MONEY + POINTS_PARTICIPATION + POINTS_TICKET_FIT + POINTS_REGION_GAP
    assert score == 100 and cautions == []
    assert any("Real-money" in r for r in reasons)
    assert any("20 past deals" in r for r in reasons)
    assert any("EUR 25m" in r and "fits" in r for r in reasons)
    assert any("UK is under-represented" in r for r in reasons)


def test_no_region_bonus_while_the_book_is_empty_or_the_region_is_well_covered() -> None:
    empty, _, _ = score_investor(investor(), deal_size_k=750_000, currency="EUR", region_share=None)
    covered, _, _ = score_investor(
        investor(), deal_size_k=750_000, currency="EUR", region_share=0.3
    )
    assert empty == covered == 85


def test_a_trading_account_without_history_gets_cautions_not_points() -> None:
    score, reasons, cautions = score_investor(
        investor(real_money=False, past_participation=0, type="hedge_fund"),
        deal_size_k=750_000,
        currency="EUR",
        region_share=0.5,
    )
    assert score == POINTS_TICKET_FIT  # only the ticket fit counts
    assert len(reasons) == 1
    assert any("Trading account" in c for c in cautions)
    assert any("No participation history" in c for c in cautions)


def test_participation_is_capped() -> None:
    capped, _, _ = score_investor(
        investor(past_participation=PARTICIPATION_CAP * 3),
        deal_size_k=750_000, currency="EUR", region_share=0.5,
    )  # fmt: skip
    assert capped == score_investor(
        investor(past_participation=PARTICIPATION_CAP),
        deal_size_k=750_000, currency="EUR", region_share=0.5,
    )[0]  # fmt: skip


def test_a_ticket_that_is_too_small_or_too_large_is_a_caution() -> None:
    _, _, small = score_investor(
        investor(ticket_mean_k=500), deal_size_k=750_000, currency="EUR", region_share=0.5
    )
    _, _, large = score_investor(
        investor(ticket_mean_k=300_000), deal_size_k=750_000, currency="EUR", region_share=0.5
    )
    assert any("small" in c and "EUR 500k" in c for c in small)
    assert any("large" in c and "EUR 300m" in c for c in large)


def test_amount_formatting() -> None:
    assert fmt_k(12_500, "USD") == "USD 12.5m"
    assert fmt_k(800, "EUR") == "EUR 800k"
