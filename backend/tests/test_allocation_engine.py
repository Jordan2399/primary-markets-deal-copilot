"""The allocation engine is pure arithmetic, so it is tested hard, including random books."""

import random

import pytest

from app.allocation.engine import (
    EngineOrder,
    allocate,
    band_for,
    priority_score,
    scale_back,
)
from app.orderbook.models import INCREMENT_K


def order(
    n: int,
    amount_k: int,
    *,
    kind: str = "asset_manager",
    minute: float = 60,
    limit: int = 100,
    past: int = 0,
    excluded: str | None = None,
) -> EngineOrder:
    return EngineOrder(
        order_id=f"O-{n:04d}",
        investor_id=f"INV-{n:03d}",
        investor_name=f"Investor {n}",
        investor_type=kind,
        amount_k=amount_k,
        limit_bp=limit,
        placed_minute=minute,
        past_participation=past,
        excluded_reason=excluded,
    )


# ------------------------------------------------------------------ scale_back


def test_scale_back_is_exact_and_never_exceeds_requests() -> None:
    result = scale_back([10, 10, 10], 20)
    assert sum(result) == 20
    assert all(0 <= got <= 10 for got in result)


def test_scale_back_gives_leftovers_to_the_largest_remainders() -> None:
    # quotas 3.33, 3.33, 3.33 -> bases 3, 3, 3, one leftover goes to the first (ties keep order)
    assert scale_back([10, 10, 10], 10) == [4, 3, 3]


def test_scale_back_returns_requests_when_everything_fits() -> None:
    assert scale_back([4, 5], 20) == [4, 5]


@pytest.mark.parametrize("seed", range(300))
def test_scale_back_random_cases(seed: int) -> None:
    rng = random.Random(seed)
    units = [rng.randint(1, 60) for _ in range(rng.randint(1, 40))]
    available = rng.randint(1, max(1, sum(units)))
    result = scale_back(units, available)
    assert sum(result) == min(available, sum(units))
    assert all(0 <= got <= asked for got, asked in zip(result, units, strict=True))


# ------------------------------------------------------------------ scoring


def test_priority_score_and_bands() -> None:
    best = order(1, 1000, kind="pension_fund", minute=10, past=9)
    assert priority_score(best) == 10 and band_for(10) == 1
    middle = order(2, 1000, kind="bank_treasury", minute=100, past=5)
    assert priority_score(middle) == 6 and band_for(6) == 2
    worst = order(3, 1000, kind="hedge_fund", minute=200, past=0)
    assert priority_score(worst) == 2 and band_for(2) == 3


# ------------------------------------------------------------------ allocate


def test_fixed_example_with_exact_numbers() -> None:
    orders = [
        order(1, 30_000, kind="pension_fund", minute=10, past=9),  # band 1
        order(2, 30_000, kind="insurer", minute=20, past=8),  # band 1
        order(3, 40_000, kind="hedge_fund", minute=200),  # band 3
    ]
    result = allocate(orders, deal_size_k=50_000, final_spread_bp=100)
    by_id = {line.order_id: line for line in result.lines}
    assert result.status == "oversubscribed"
    assert result.total_allocated_k == 50_000
    # band 1 asked for 60,000 and shares 50,000 pro rata; band 3 gets nothing
    assert by_id["O-0001"].allocated_k == 25_000 and by_id["O-0002"].allocated_k == 25_000
    assert by_id["O-0003"].allocated_k == 0
    assert "No allocation" in by_id["O-0003"].note
    assert [b.band for b in result.bands] == [1, 3]


def test_higher_band_is_served_before_lower_band() -> None:
    orders = [
        order(1, 20_000, kind="pension_fund", minute=5, past=10),
        order(2, 20_000, kind="hedge_fund", minute=230),
    ]
    result = allocate(orders, deal_size_k=20_000, final_spread_bp=100)
    by_id = {line.order_id: line for line in result.lines}
    assert by_id["O-0001"].allocated_k == 20_000
    assert by_id["O-0002"].allocated_k == 0


def test_undersubscribed_book_fills_everyone_and_reports_shortfall() -> None:
    orders = [order(1, 10_000), order(2, 15_000)]
    result = allocate(orders, deal_size_k=50_000, final_spread_bp=100)
    assert result.status == "undersubscribed"
    assert result.total_allocated_k == 25_000
    assert all(line.fill_pct == 100.0 for line in result.lines)


def test_excluded_and_dropped_out_orders_get_nothing() -> None:
    orders = [
        order(1, 10_000),
        order(2, 10_000, excluded="after close"),
        order(3, 10_000, limit=90),  # wants a tighter spread than the final 100
    ]
    result = allocate(orders, deal_size_k=50_000, final_spread_bp=100)
    by_id = {line.order_id: line for line in result.lines}
    # limit 90 is at or below 100, so it stays in; only the excluded one is out
    assert by_id["O-0002"].allocated_k == 0 and by_id["O-0002"].band is None
    assert by_id["O-0003"].allocated_k == 10_000

    tight = allocate([order(1, 10_000, limit=105)], deal_size_k=5_000, final_spread_bp=100)
    assert tight.lines[0].allocated_k == 0 and "Dropped out" in tight.lines[0].note


def test_amounts_are_rounded_down_to_the_increment() -> None:
    result = allocate([order(1, 10_050)], deal_size_k=50_000, final_spread_bp=100)
    assert result.lines[0].allocated_k == 10_000


@pytest.mark.parametrize("seed", range(500))
def test_oversubscribed_allocation_always_sums_to_deal_size(seed: int) -> None:
    """The Day 2 gate: allocation always sums to the deal size."""
    rng = random.Random(seed)
    kinds = ["pension_fund", "insurer", "asset_manager", "bank_treasury", "hedge_fund"]
    deal_size_k = rng.choice([50_000, 300_000, 750_000, 1_500_000])
    orders: list[EngineOrder] = []
    total = 0
    n = 0
    while total < deal_size_k * rng.uniform(1.05, 4.0):
        n += 1
        amount = rng.randrange(1_000, max(2_000, deal_size_k // 4), 100)
        total += amount
        orders.append(
            order(
                n,
                amount,
                kind=rng.choice(kinds),
                minute=rng.uniform(0, 239),
                limit=rng.randrange(80, 101, 5),
                past=rng.randint(0, 12),
            )
        )
    spread = rng.randrange(80, 101, 5)
    result = allocate(orders, deal_size_k, spread)
    if result.status == "undersubscribed":
        assert result.total_allocated_k == result.eligible_demand_k < deal_size_k
    else:
        assert result.status in ("oversubscribed", "fully covered")
        assert result.total_allocated_k == deal_size_k
    for line in result.lines:
        assert line.allocated_k % INCREMENT_K == 0
        assert line.allocated_k <= line.ordered_k
    # nothing is given to an order that dropped out
    dropped = {o.order_id for o in orders if o.limit_bp > spread}
    assert all(line.allocated_k == 0 for line in result.lines if line.order_id in dropped)
