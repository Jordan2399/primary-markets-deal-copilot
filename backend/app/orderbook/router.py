"""Order book endpoints. Syndicate desks work the book; approvers may read it."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, Role, get_current_user, require_roles
from app.deps import get_orderbook_service
from app.orderbook.models import Anomaly, OrderBook, SimulateRequest
from app.orderbook.service import OrderBookService

router = APIRouter(tags=["orderbook"], dependencies=[Depends(get_current_user)])

Service = Annotated[OrderBookService, Depends(get_orderbook_service)]
CanRead = Annotated[CurrentUser, Depends(require_roles(Role.syndicate, Role.approver))]
CanSimulate = Annotated[CurrentUser, Depends(require_roles(Role.syndicate))]


@router.get("/deals/{deal_id}/orderbook", response_model=OrderBook)
async def get_orderbook(deal_id: str, service: Service, _user: CanRead) -> OrderBook:
    """Orders, anomalies and live metrics for the deal's book."""
    return await service.get_book(deal_id)


@router.post("/deals/{deal_id}/orderbook/simulate", response_model=OrderBook)
async def simulate_orderbook(
    deal_id: str, request: SimulateRequest, service: Service, user: CanSimulate
) -> OrderBook:
    """Generate (or extend) a seeded, synthetic book. Only from Book building onwards."""
    return await service.simulate(deal_id, request, user)


@router.get("/deals/{deal_id}/orderbook/anomalies", response_model=list[Anomaly])
async def get_anomalies(deal_id: str, service: Service, _user: CanRead) -> list[Anomaly]:
    return (await service.get_book(deal_id)).anomalies
