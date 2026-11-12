"""Anomaly rules. Pure functions: no database, no model, fully unit-testable.

Rules and what they do to an allocation:
- after_close        order placed after the book closed            -> excluded
- exceeds_deal_size  order larger than the whole deal              -> excluded
- duplicate          same investor, same limit, more than once      -> later copies excluded
- ticket_zscore      order far above the investor's usual ticket    -> flagged for review only
"""

from collections import defaultdict

from app.orderbook.models import Anomaly, BookParams, OrderRow

ZSCORE_LIMIT = 3.0


def detect_anomalies(
    orders: list[OrderRow], params: BookParams | None, deal_size_k: int
) -> list[Anomaly]:
    found: list[Anomaly] = []

    seen: dict[tuple[str, int], list[OrderRow]] = defaultdict(list)
    for order in sorted(orders, key=lambda o: (o.placed_at, o.id)):
        seen[(order.investor_id, order.limit_bp)].append(order)
    for group in seen.values():
        for later in group[1:]:
            found.append(
                Anomaly(
                    order_id=later.id,
                    rule="duplicate",
                    severity="high",
                    excludes=True,
                    message=(
                        f"{later.investor_name} already has order {group[0].id} at the same limit "
                        f"({later.limit_bp}bp); this copy is excluded."
                    ),
                )
            )

    for order in orders:
        if params is not None and order.placed_at > params.close_at:
            found.append(
                Anomaly(
                    order_id=order.id,
                    rule="after_close",
                    severity="high",
                    excludes=True,
                    message=f"Placed at {order.placed_at:%H:%M}, after the book closed at {params.close_at:%H:%M}.",
                )
            )
        if order.amount_k > deal_size_k:
            found.append(
                Anomaly(
                    order_id=order.id,
                    rule="exceeds_deal_size",
                    severity="high",
                    excludes=True,
                    message=f"Order of {order.amount_k:,}k is larger than the deal ({deal_size_k:,}k).",
                )
            )
        if order.ticket_std_k > 0:
            z = (order.amount_k - order.ticket_mean_k) / order.ticket_std_k
            if z > ZSCORE_LIMIT:
                found.append(
                    Anomaly(
                        order_id=order.id,
                        rule="ticket_zscore",
                        severity="medium",
                        excludes=False,
                        message=(
                            f"{order.amount_k:,}k is {z:.1f} standard deviations above this investor's "
                            f"usual ticket of {order.ticket_mean_k:,}k."
                        ),
                    )
                )
    return sorted(found, key=lambda a: (a.order_id, a.rule))


def excluded_order_ids(anomalies: list[Anomaly]) -> set[str]:
    return {a.order_id for a in anomalies if a.excludes}
