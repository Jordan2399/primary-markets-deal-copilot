from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import ConflictError
from app.deals.service import DealService
from app.investors.generator import build_investors
from app.orderbook.anomalies import detect_anomalies
from app.orderbook.generator import BOOK_MINUTES, default_params, generate_orders
from app.orderbook.metrics import build_ladder, compute_metrics, suggest_final_spread
from app.orderbook.models import BookParams, OrderRow, SimulateRequest
from app.orderbook.service import OrderBookService
from tests.fakes import (
    ADMIN,
    SYNDICATE,
    FakeDealRepository,
    FakeOrderBookRepository,
    add_deal,
)

OPEN = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
PARAMS = BookParams(open_at=OPEN, close_at=OPEN + timedelta(minutes=240), ipt_bp=100)


def row(
    n: int,
    amount_k: int,
    *,
    investor: str = "INV-001",
    limit: int = 100,
    minute: int = 30,
    mean: int = 20_000,
    std: int = 5_000,
    kind: str = "asset_manager",
    region: str = "UK",
    real_money: bool = True,
) -> OrderRow:
    return OrderRow(
        id=f"O-{n:04d}",
        investor_id=investor,
        investor_name=f"Investor {investor}",
        investor_type=kind,
        region=region,
        real_money=real_money,
        ticket_mean_k=mean,
        ticket_std_k=std,
        past_participation=3,
        amount_k=amount_k,
        limit_bp=limit,
        placed_at=OPEN + timedelta(minutes=minute),
    )


# ------------------------------------------------------------------ investors and generator


def test_150_unique_investors_with_all_types() -> None:
    investors = build_investors()
    assert len(investors) == 150
    assert len({i.id for i in investors}) == 150
    assert len({i.name for i in investors}) == 150
    assert {i.type for i in investors} == {
        "asset_manager",
        "insurer",
        "pension_fund",
        "bank_treasury",
        "official_institution",
        "hedge_fund",
    }
    assert investors == build_investors()  # deterministic


def test_generator_is_deterministic_and_reaches_the_target_cover() -> None:
    investors = build_investors()
    args = dict(
        deal_id="D-1",
        deal_size_k=500_000,
        investors=investors,
        params=PARAMS,
        seed=1,
        target_cover=2.5,
        anomalies=0,
    )
    first = generate_orders(**args)  # type: ignore[arg-type]
    assert first == generate_orders(**args)  # type: ignore[arg-type]
    total = sum(o.amount_k for o in first)
    assert 2.5 * 500_000 <= total < 2.5 * 500_000 + 130_000
    assert len({o.id for o in first}) == len(first)
    assert all(PARAMS.open_at <= o.placed_at <= PARAMS.close_at for o in first)
    assert all(o.amount_k % 500 == 0 for o in first)


def test_waves_and_tightening_limits() -> None:
    orders = generate_orders(
        deal_id="D-1",
        deal_size_k=1_000_000,
        investors=build_investors(),
        params=PARAMS,
        seed=2,
        target_cover=3.5,
        anomalies=0,
    )
    early = [o for o in orders if (o.placed_at - OPEN).total_seconds() / 60 < 30]
    late = [o for o in orders if (o.placed_at - OPEN).total_seconds() / 60 >= 200]
    assert early and late
    assert min(o.limit_bp for o in late) < min(o.limit_bp for o in early)
    assert all(o.limit_bp >= PARAMS.ipt_bp - 10 for o in early)


def test_different_seeds_give_different_books() -> None:
    kwargs = dict(
        deal_id="D-1",
        deal_size_k=500_000,
        investors=build_investors(),
        params=PARAMS,
        target_cover=2.5,
        anomalies=0,
    )
    a = generate_orders(seed=1, **kwargs)  # type: ignore[arg-type]
    b = generate_orders(seed=2, **kwargs)  # type: ignore[arg-type]
    assert [o.amount_k for o in a] != [o.amount_k for o in b]


def test_default_params_are_a_four_hour_window() -> None:
    params = default_params("D-9", datetime(2026, 11, 10, tzinfo=UTC))
    assert (params.close_at - params.open_at).total_seconds() == BOOK_MINUTES * 60
    assert params == default_params("D-9", datetime(2026, 11, 10, tzinfo=UTC))
    assert 70 <= params.ipt_bp < 135


# ------------------------------------------------------------------ anomaly rules


def test_duplicate_rule_flags_later_copy_only() -> None:
    orders = [row(1, 10_000, minute=10), row(2, 10_000, minute=20)]
    found = detect_anomalies(orders, PARAMS, 500_000)
    assert [(a.order_id, a.rule, a.excludes) for a in found] == [("O-0002", "duplicate", True)]


def test_different_limit_is_not_a_duplicate() -> None:
    orders = [row(1, 10_000, limit=100), row(2, 10_000, limit=95)]
    assert detect_anomalies(orders, PARAMS, 500_000) == []


def test_after_close_and_oversize_rules() -> None:
    orders = [
        row(1, 10_000, investor="A", minute=241),
        row(2, 600_000, investor="B", minute=20),
    ]
    rules = {(a.order_id, a.rule) for a in detect_anomalies(orders, PARAMS, 500_000)}
    assert ("O-0001", "after_close") in rules
    assert ("O-0002", "exceeds_deal_size") in rules


def test_zscore_rule_flags_but_does_not_exclude() -> None:
    order = row(1, 20_000 + 4 * 5_000)  # four standard deviations above the mean
    [found] = detect_anomalies([order], PARAMS, 500_000)
    assert found.rule == "ticket_zscore" and found.excludes is False
    assert (
        detect_anomalies([row(1, 20_000 + 3 * 5_000)], PARAMS, 500_000) == []
    )  # exactly 3 is fine


def test_generator_injects_each_kind_of_anomaly() -> None:
    investors = build_investors()
    orders = generate_orders(
        deal_id="D-1",
        deal_size_k=500_000,
        investors=investors,
        params=PARAMS,
        seed=1,
        target_cover=2.5,
        anomalies=4,
    )
    by_id = {i.id: i for i in investors}
    rows = [
        OrderRow(
            id=o.id,
            investor_id=o.investor_id,
            investor_name="x",
            investor_type="asset_manager",
            region="UK",
            real_money=True,
            ticket_mean_k=by_id[o.investor_id].ticket_mean_k,
            ticket_std_k=by_id[o.investor_id].ticket_std_k,
            past_participation=1,
            amount_k=o.amount_k,
            limit_bp=o.limit_bp,
            placed_at=o.placed_at,
        )
        for o in orders
    ]
    rules = {a.rule for a in detect_anomalies(rows, PARAMS, 500_000)}
    assert rules == {"duplicate", "ticket_zscore", "after_close", "exceeds_deal_size"}


def test_clean_books_have_no_natural_anomalies() -> None:
    investors = build_investors()
    for seed in range(20):
        orders = generate_orders(
            deal_id="D-1",
            deal_size_k=500_000,
            investors=investors,
            params=PARAMS,
            seed=seed,
            target_cover=3.0,
            anomalies=0,
        )
        by_id = {i.id: i for i in investors}
        rows = [
            OrderRow(
                id=o.id,
                investor_id=o.investor_id,
                investor_name="x",
                investor_type="asset_manager",
                region="UK",
                real_money=True,
                ticket_mean_k=by_id[o.investor_id].ticket_mean_k,
                ticket_std_k=by_id[o.investor_id].ticket_std_k,
                past_participation=1,
                amount_k=o.amount_k,
                limit_bp=o.limit_bp,
                placed_at=o.placed_at,
            )
            for o in orders
        ]
        assert detect_anomalies(rows, PARAMS, 500_000) == [], seed


# ------------------------------------------------------------------ metrics


def test_metrics_exclude_flagged_orders_from_cover() -> None:
    orders = [
        row(1, 100_000, investor="A", minute=10, kind="pension_fund", region="UK"),
        row(2, 100_000, investor="B", minute=20, kind="hedge_fund", region="US", real_money=False),
        row(3, 50_000, investor="C", minute=250),  # after close: excluded
    ]
    anomalies = detect_anomalies(orders, PARAMS, 100_000)
    metrics = compute_metrics(orders, anomalies, PARAMS, 100_000)
    assert metrics.total_demand_k == 250_000
    assert metrics.valid_demand_k == 200_000
    assert metrics.cover_ratio == 2.0
    assert metrics.valid_order_count == 2 and metrics.investor_count == 2
    assert metrics.real_money_share_pct == 50.0
    assert {b.label for b in metrics.by_type} == {"pension_fund", "hedge_fund"}
    assert sum(b.share_pct for b in metrics.by_region) == pytest.approx(100.0)


def test_ladder_is_cumulative_and_suggestion_keeps_cover() -> None:
    orders = [
        row(1, 100_000, investor="A", limit=80),
        row(2, 100_000, investor="B", limit=90),
        row(3, 100_000, investor="C", limit=100),
    ]
    ladder = build_ladder(orders, 100_000, 100)
    demands = [level.demand_k for level in ladder]
    assert demands == sorted(demands)
    assert ladder[0].spread_bp == 80 and ladder[-1].demand_k == 300_000
    assert suggest_final_spread(ladder) == 90  # 90bp keeps 2.0x cover, 80bp only 1.0x
    assert suggest_final_spread([]) is None


def test_timeline_is_cumulative() -> None:
    orders = [row(1, 10_000, minute=5), row(2, 10_000, investor="B", minute=100)]
    metrics = compute_metrics(orders, [], PARAMS, 20_000)
    values = [p.cumulative_demand_k for p in metrics.timeline]
    assert (
        values == sorted(values) and values[-1] == 20_000 and values[0] == 0 and values[1] == 10_000
    )
    assert metrics.timeline[-1].minute == 240


# ------------------------------------------------------------------ service


@pytest.fixture
def parts() -> tuple[FakeDealRepository, FakeOrderBookRepository, OrderBookService]:
    deals = FakeDealRepository()
    book_repo = FakeOrderBookRepository(deals.events)
    return deals, book_repo, OrderBookService(book_repo, DealService(deals))


async def test_simulate_is_refused_before_book_building(parts) -> None:  # type: ignore[no-untyped-def]
    deals, _, service = parts
    await add_deal(deals, stage_code="documentation")
    with pytest.raises(ConflictError, match="Book building"):
        await service.simulate("D-DEMO-001", SimulateRequest(), SYNDICATE)


async def test_simulate_creates_a_book_with_metrics_and_audit(parts) -> None:  # type: ignore[no-untyped-def]
    deals, _, service = parts
    await add_deal(deals, stage_code="book_building", done_in_stage=0)
    book = await service.simulate(
        "D-DEMO-001", SimulateRequest(seed=3, target_cover=3.0), SYNDICATE
    )
    assert book.metrics is not None and book.params is not None
    assert book.metrics.cover_ratio > 2.0
    assert len(book.orders) == book.metrics.order_count
    assert {a.rule for a in book.anomalies} == {
        "duplicate",
        "ticket_zscore",
        "after_close",
        "exceeds_deal_size",
    }
    event = deals.events[-1]
    assert event.action == "orderbook.simulate" and event.details["orders_created"] == len(
        book.orders
    )


async def test_simulate_replaces_unless_extending(parts) -> None:  # type: ignore[no-untyped-def]
    deals, _, service = parts
    await add_deal(deals, stage_code="book_building", done_in_stage=0)
    first = await service.simulate("D-DEMO-001", SimulateRequest(seed=1, anomalies=0), ADMIN)
    again = await service.simulate("D-DEMO-001", SimulateRequest(seed=1, anomalies=0), ADMIN)
    assert [o.id for o in again.orders] == [o.id for o in first.orders]
    extended = await service.simulate(
        "D-DEMO-001", SimulateRequest(seed=2, anomalies=0, extend=True, target_cover=1.0), ADMIN
    )
    assert len(extended.orders) > len(first.orders)
    assert len({o.id for o in extended.orders}) == len(extended.orders)
    assert len({o.investor_id for o in extended.orders}) == len(extended.orders)


async def test_empty_book_has_no_metrics(parts) -> None:  # type: ignore[no-untyped-def]
    deals, _, service = parts
    await add_deal(deals, stage_code="documentation")
    book = await service.get_book("D-DEMO-001")
    assert book.metrics is None and book.orders == []
