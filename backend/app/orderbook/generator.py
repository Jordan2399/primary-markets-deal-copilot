"""Seeded order generator.

Orders arrive in three waves over a four-hour window: an early anchor wave of large tickets,
a mid-day build, and a final hour where spread limits tighten as guidance firms up. A few
deliberate anomalies can be injected so the anomaly rules have something to find.
"""

import random
from datetime import datetime, timedelta

from app.investors.models import Investor
from app.orderbook.models import INCREMENT_K, BookParams, NewOrder

SEED_VALUE = "deal-copilot-2026"
BOOK_MINUTES = 240


def default_params(deal_id: str, launch: datetime) -> BookParams:
    """Book window and initial price thoughts for a deal: deterministic per deal id."""
    rng = random.Random(f"{SEED_VALUE}-{deal_id}-params")
    open_at = launch.replace(hour=8, minute=0, second=0, microsecond=0)
    return BookParams(
        open_at=open_at,
        close_at=open_at + timedelta(minutes=BOOK_MINUTES),
        ipt_bp=rng.randrange(70, 135, 5),
    )


def _round_amount(value: float) -> int:
    return max(1_000, int(round(value / 500) * 500))


def _wave(rng: random.Random, fraction: float) -> tuple[int, int, list[int]]:
    """Return (start minute, end minute, allowed limit offsets below IPT) for the wave."""
    if fraction < 0.18:
        return 0, 30, [0, 0, 5]
    if fraction < 0.80:
        return 30, 200, [0, 5, 10, 15]
    return 200, BOOK_MINUTES, [10, 15, 20, 25]


def generate_orders(
    *,
    deal_id: str,
    deal_size_k: int,
    investors: list[Investor],
    params: BookParams,
    seed: int,
    target_cover: float,
    anomalies: int,
    skip_investors: set[str] | None = None,
    start_index: int = 1,
) -> list[NewOrder]:
    rng = random.Random(f"{SEED_VALUE}-{deal_id}-{seed}-{start_index}")
    pool = [i for i in investors if i.id not in (skip_investors or set())]
    rng.shuffle(pool)
    target = deal_size_k * target_cover

    drawn: list[tuple[Investor, int]] = []
    total = 0
    for investor in pool:
        if total >= target:
            break
        amount = rng.gauss(investor.ticket_mean_k, investor.ticket_std_k)
        amount = min(amount, investor.ticket_mean_k + 2.5 * investor.ticket_std_k)
        amount = min(_round_amount(amount), deal_size_k // 4)
        drawn.append((investor, amount))
        total += amount

    orders: list[NewOrder] = []
    count = len(drawn)
    for position, (investor, amount) in enumerate(drawn):
        start, end, offsets = _wave(rng, position / max(count, 1))
        placed = params.open_at + timedelta(minutes=rng.uniform(start, end - 1))
        orders.append(
            NewOrder(
                id=f"{deal_id}:O-{start_index + position:04d}",
                investor_id=investor.id,
                amount_k=amount,
                limit_bp=params.ipt_bp - rng.choice(offsets),
                placed_at=placed,
            )
        )

    next_index = start_index + len(orders)
    for n in range(anomalies):
        if not orders:
            break
        kind = n % 4
        order_id = f"{deal_id}:O-{next_index + n:04d}"
        base = orders[rng.randrange(len(orders))]
        investor = next(i for i in investors if i.id == base.investor_id)
        if kind == 0:  # duplicate: same investor, same limit, a little later
            orders.append(
                base.model_copy(
                    update={"id": order_id, "placed_at": base.placed_at + timedelta(minutes=3)}
                )
            )
        elif kind == 1:  # far above the investor's usual ticket
            amount = _round_amount(investor.ticket_mean_k + 5 * investor.ticket_std_k)
            orders.append(
                base.model_copy(
                    update={"id": order_id, "amount_k": min(amount, deal_size_k - INCREMENT_K)}
                )
            )
        elif kind == 2:  # placed after the close
            orders.append(
                base.model_copy(
                    update={"id": order_id, "placed_at": params.close_at + timedelta(minutes=7)}
                )
            )
        else:  # larger than the whole deal
            oversized = ((int(deal_size_k * 1.2) + INCREMENT_K - 1) // INCREMENT_K) * INCREMENT_K
            orders.append(base.model_copy(update={"id": order_id, "amount_k": oversized}))
    return orders
