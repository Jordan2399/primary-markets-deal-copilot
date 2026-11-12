"""Order book rules: who may simulate, when, and how the book is read."""

from dataclasses import dataclass
from datetime import UTC, datetime, time

from app.audit.models import build_event
from app.core.errors import ConflictError
from app.core.security import CurrentUser
from app.deals.models import DealDetail
from app.deals.service import DealService
from app.deals.templates import STAGE_BY_CODE
from app.orderbook.anomalies import detect_anomalies
from app.orderbook.generator import default_params, generate_orders
from app.orderbook.metrics import compute_metrics
from app.orderbook.models import (
    Anomaly,
    BookParams,
    OrderBook,
    OrderOut,
    OrderRow,
    SimulateRequest,
)
from app.orderbook.repository import OrderBookRepository

BOOK_BUILDING_POSITION = STAGE_BY_CODE["book_building"].position


@dataclass
class BookState:
    """Everything the allocation needs to know about a deal's book."""

    deal: DealDetail
    deal_size_k: int
    params: BookParams | None
    orders: list[OrderRow]
    anomalies: list[Anomaly]


class OrderBookService:
    def __init__(self, repo: OrderBookRepository, deals: DealService) -> None:
        self._repo = repo
        self._deals = deals

    async def state(self, deal_id: str) -> BookState:
        deal = await self._deals.get_deal(deal_id)
        size_k = int(deal.size_mm * 1000)
        params = await self._repo.get_params(deal_id)
        orders = await self._repo.list_orders(deal_id)
        anomalies = detect_anomalies(orders, params, size_k)
        return BookState(deal, size_k, params, orders, anomalies)

    async def get_book(self, deal_id: str) -> OrderBook:
        state = await self.state(deal_id)
        flags: dict[str, list[str]] = {}
        for a in state.anomalies:
            flags.setdefault(a.order_id, []).append(a.rule)
        metrics = (
            compute_metrics(state.orders, state.anomalies, state.params, state.deal_size_k)
            if state.orders
            else None
        )
        return OrderBook(
            deal_id=deal_id,
            params=state.params,
            metrics=metrics,
            orders=[
                OrderOut(
                    **o.model_dump(include=set(OrderOut.model_fields) - {"flags"}),
                    flags=flags.get(o.id, []),
                )
                for o in state.orders
            ],
            anomalies=state.anomalies,
        )

    async def simulate(
        self, deal_id: str, request: SimulateRequest, user: CurrentUser
    ) -> OrderBook:
        deal = await self._deals.get_deal(deal_id)
        if deal.stage_position < BOOK_BUILDING_POSITION:
            raise ConflictError(
                "The order book opens at the Book building stage. "
                f"This deal is at {deal.stage_name}.",
                details={"stage": deal.stage_code},
            )
        investors = await self._repo.list_investors()
        if not investors:
            raise ConflictError("There are no investors yet. Run the seed to load them.")

        existing = await self._repo.list_orders(deal_id) if request.extend else []
        params = await self._repo.get_params(deal_id) if request.extend else None
        if params is None:
            launch = datetime.combine(
                deal.launch_date or datetime.now(UTC).date(), time(0), tzinfo=UTC
            )
            params = default_params(deal_id, launch)

        orders = generate_orders(
            deal_id=deal_id,
            deal_size_k=int(deal.size_mm * 1000),
            investors=investors,
            params=params,
            seed=request.seed,
            target_cover=request.target_cover,
            anomalies=request.anomalies,
            skip_investors={o.investor_id for o in existing},
            start_index=len(existing) + 1,
        )
        event = build_event(
            user,
            "orderbook.simulate",
            "deal",
            deal_id,
            deal_id=deal_id,
            details={
                "seed": request.seed,
                "target_cover": request.target_cover,
                "anomalies": request.anomalies,
                "extend": request.extend,
                "orders_created": len(orders),
            },
        )
        await self._repo.save_book(deal_id, params, orders, replace=not request.extend, event=event)
        return await self.get_book(deal_id)
