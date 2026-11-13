"""Book metrics. Pure functions: every number the UI shows is computed here, not in the browser."""

from collections import defaultdict

from app.orderbook.models import (
    Anomaly,
    BookMetrics,
    BookParams,
    Bucket,
    LadderLevel,
    OrderRow,
    TimelinePoint,
)

LADDER_STEP_BP = 5
MIN_COVER_FOR_SUGGESTION = 1.5


def _buckets(rows: list[tuple[str, int]]) -> list[Bucket]:
    demand: dict[str, int] = defaultdict(int)
    count: dict[str, int] = defaultdict(int)
    for label, amount in rows:
        demand[label] += amount
        count[label] += 1
    total = sum(demand.values()) or 1
    return [
        Bucket(
            label=label,
            demand_k=value,
            orders=count[label],
            share_pct=round(100 * value / total, 1),
        )
        for label, value in sorted(demand.items(), key=lambda kv: -kv[1])
    ]


def build_ladder(valid: list[OrderRow], deal_size_k: int, ipt_bp: int) -> list[LadderLevel]:
    """Cumulative demand that is still in the book at each possible final spread.

    A wider spread keeps more orders in, so demand rises as the spread widens.
    """
    if not valid:
        return []
    lowest = min(o.limit_bp for o in valid)
    start = (lowest // LADDER_STEP_BP) * LADDER_STEP_BP
    stop = max(ipt_bp, max(o.limit_bp for o in valid))
    levels: list[LadderLevel] = []
    for spread in range(start, stop + LADDER_STEP_BP, LADDER_STEP_BP):
        demand = sum(o.amount_k for o in valid if o.limit_bp <= spread)
        levels.append(
            LadderLevel(spread_bp=spread, demand_k=demand, cover=round(demand / deal_size_k, 2))
        )
    return levels


def suggest_final_spread(ladder: list[LadderLevel]) -> int | None:
    """The tightest spread that still keeps the book covered at least 1.5 times."""
    if not ladder:
        return None
    for level in ladder:  # ladder runs from tight to wide
        if level.cover >= MIN_COVER_FOR_SUGGESTION:
            return level.spread_bp
    return ladder[-1].spread_bp


def compute_metrics(
    orders: list[OrderRow], anomalies: list[Anomaly], params: BookParams | None, deal_size_k: int
) -> BookMetrics:
    excluded = {a.order_id for a in anomalies if a.excludes}
    valid = [o for o in orders if o.id not in excluded]
    valid_demand = sum(o.amount_k for o in valid)
    real_money = sum(o.amount_k for o in valid if o.real_money)

    timeline: list[TimelinePoint] = []
    if params is not None and valid:
        span = int((params.close_at - params.open_at).total_seconds() // 60)
        for minute in range(0, span + 1, 15):
            upto = [
                o for o in valid if (o.placed_at - params.open_at).total_seconds() / 60 <= minute
            ]
            timeline.append(
                TimelinePoint(
                    minute=minute,
                    cumulative_demand_k=sum(o.amount_k for o in upto),
                    orders=len(upto),
                )
            )

    ladder = build_ladder(valid, deal_size_k, params.ipt_bp if params else 0)
    return BookMetrics(
        deal_size_k=deal_size_k,
        order_count=len(orders),
        valid_order_count=len(valid),
        investor_count=len({o.investor_id for o in valid}),
        total_demand_k=sum(o.amount_k for o in orders),
        valid_demand_k=valid_demand,
        cover_ratio=round(valid_demand / deal_size_k, 2) if deal_size_k else 0.0,
        real_money_share_pct=round(100 * real_money / valid_demand, 1) if valid_demand else 0.0,
        anomaly_count=len(anomalies),
        by_type=_buckets([(o.investor_type, o.amount_k) for o in valid]),
        by_region=_buckets([(o.region, o.amount_k) for o in valid]),
        ladder=ladder,
        timeline=timeline,
        suggested_final_spread_bp=suggest_final_spread(ladder),
    )
