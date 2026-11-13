"""The allocation engine. Pure integer arithmetic: no database, no model, no floats in the maths.

How an order gets its units:

1. Eligibility. An order takes part only if it was not excluded by an anomaly rule and its
   spread limit is at or below the final spread (it stays in the book at that price).
2. Priority score = 2 x type points + timing points + participation points (maximum 10)
     type:          pension fund, insurer, asset manager, official institution 3; bank treasury 2;
                    hedge fund 1
     timing:        placed in the first 30 minutes 2; in the first two hours 1; later 0
     participation: 8 or more past deals 2; 4 or more 1; otherwise 0
   Score 8 and above is band 1, 6 and 7 is band 2, below 6 is band 3.
3. Bands are served in order. If a band's demand fits in what is left, every order is filled in
   full. Otherwise the orders in that band are scaled back pro rata and the lower bands get
   nothing.
4. Rounding. Amounts are in whole increments of the minimum denomination. Each order's
   scaled amount is rounded down to an increment; the units that are left over are handed out one
   increment at a time by the largest remainder method, so the total matches exactly.

If the eligible demand is no larger than the deal, everyone is filled in full. The status says
"fully covered" when it matches the deal exactly and "undersubscribed" when it falls short.
"""

from dataclasses import dataclass

from app.allocation.models import AllocationLine, AllocationResult, BandSummary
from app.orderbook.models import INCREMENT_K

TYPE_POINTS = {
    "pension_fund": 3,
    "insurer": 3,
    "asset_manager": 3,
    "official_institution": 3,
    "bank_treasury": 2,
    "hedge_fund": 1,
}


@dataclass(frozen=True)
class EngineOrder:
    order_id: str
    investor_id: str
    investor_name: str
    investor_type: str
    amount_k: int
    limit_bp: int
    placed_minute: float  # minutes after the book opened
    past_participation: int
    excluded_reason: str | None = None  # set when an anomaly rule excludes the order


def priority_score(order: EngineOrder) -> int:
    type_points = TYPE_POINTS.get(order.investor_type, 1)
    timing = 2 if order.placed_minute <= 30 else 1 if order.placed_minute <= 120 else 0
    participation = (
        2 if order.past_participation >= 8 else 1 if order.past_participation >= 4 else 0
    )
    return type_points * 2 + timing + participation


def band_for(score: int) -> int:
    return 1 if score >= 8 else 2 if score >= 6 else 3


def scale_back(units: list[int], available: int) -> list[int]:
    """Share `available` units across orders pro rata, rounding down, then largest remainder.

    `units[i]` is what order i asked for. The result never exceeds a request and sums to
    `available` exactly (when the requests add up to more than `available`).
    """
    demand = sum(units)
    if demand <= available:
        return list(units)
    base = [(u * available) // demand for u in units]
    remainders = [(u * available) % demand for u in units]
    leftover = available - sum(base)
    ranked = sorted(range(len(units)), key=lambda i: (-remainders[i], -units[i], i))
    for i in ranked[:leftover]:
        base[i] += 1
    return base


def _status(eligible_demand_k: int, deal_size_k: int) -> str:
    if eligible_demand_k > deal_size_k:
        return "oversubscribed"
    return "fully covered" if eligible_demand_k == deal_size_k else "undersubscribed"


def allocate(
    orders: list[EngineOrder],
    deal_size_k: int,
    final_spread_bp: int,
    increment_k: int = INCREMENT_K,
) -> AllocationResult:
    size_units = deal_size_k // increment_k
    scored: dict[str, tuple[int, int]] = {}
    eligible: list[EngineOrder] = []
    notes: dict[str, str] = {}
    for order in orders:
        if order.excluded_reason:
            notes[order.order_id] = f"Excluded: {order.excluded_reason}."
        elif order.limit_bp > final_spread_bp:
            notes[order.order_id] = (
                f"Dropped out: limit {order.limit_bp}bp is tighter than the final spread {final_spread_bp}bp."
            )
        elif order.amount_k // increment_k <= 0:
            notes[order.order_id] = "Excluded: below the minimum denomination."
        else:
            eligible.append(order)
            score = priority_score(order)
            scored[order.order_id] = (score, band_for(score))

    allocated: dict[str, int] = {}
    remaining = size_units
    band_summaries: list[BandSummary] = []
    for band in (1, 2, 3):
        members = sorted(
            (o for o in eligible if scored[o.order_id][1] == band),
            key=lambda o: (o.placed_minute, o.order_id),
        )
        if not members:
            continue
        requested = [o.amount_k // increment_k for o in members]
        given = scale_back(requested, remaining) if remaining > 0 else [0] * len(members)
        for order, units, asked in zip(members, given, requested, strict=True):
            allocated[order.order_id] = units
            if units == asked:
                notes[order.order_id] = "Filled in full."
            elif units == 0:
                notes[order.order_id] = "No allocation: higher bands used the whole deal."
            else:
                notes[order.order_id] = (
                    f"Scaled back to {round(100 * units / asked)}% of the order."
                )
        remaining -= sum(given)
        demand = sum(requested)
        band_summaries.append(
            BandSummary(
                band=band,
                orders=len(members),
                demand_k=demand * increment_k,
                allocated_k=sum(given) * increment_k,
                scale_pct=round(100 * sum(given) / demand, 1) if demand else 0.0,
            )
        )

    lines: list[AllocationLine] = []
    for order in orders:
        got = allocated.get(order.order_id, 0) * increment_k
        pair = scored.get(order.order_id)
        line_score = pair[0] if pair else None
        line_band = pair[1] if pair else None
        lines.append(
            AllocationLine(
                order_id=order.order_id,
                investor_id=order.investor_id,
                investor_name=order.investor_name,
                investor_type=order.investor_type,
                band=line_band,
                score=line_score,
                ordered_k=order.amount_k,
                allocated_k=got,
                fill_pct=round(100 * got / order.amount_k, 1) if order.amount_k else 0.0,
                note=notes.get(order.order_id, ""),
            )
        )
    eligible_demand = sum((o.amount_k // increment_k) * increment_k for o in eligible)
    total = sum(allocated.values()) * increment_k
    return AllocationResult(
        deal_size_k=deal_size_k,
        final_spread_bp=final_spread_bp,
        eligible_demand_k=eligible_demand,
        total_allocated_k=total,
        status=_status(eligible_demand, size_units * increment_k),
        bands=band_summaries,
        lines=lines,
    )
