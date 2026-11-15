"""Investor endpoints. Read-only; the desks that sell the deal may look, viewers may not."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.core.security import CurrentUser, Role, get_current_user, require_roles
from app.deps import get_investor_service
from app.investors.models import DealNetwork, InvestorPage, InvestorProfile, Target
from app.investors.service import SORT_KEYS, InvestorService

router = APIRouter(tags=["investors"], dependencies=[Depends(get_current_user)])

Service = Annotated[InvestorService, Depends(get_investor_service)]
# Admin always passes (see require_roles). Viewers are left out: investor data is commercially
# sensitive even when, as here, it is synthetic.
CanRead = Annotated[
    CurrentUser, Depends(require_roles(Role.marketer, Role.syndicate, Role.approver))
]


@router.get("/investors", response_model=InvestorPage)
async def list_investors(
    service: Service,
    _user: CanRead,
    q: Annotated[str | None, Query(max_length=60, description="Name contains, or exact id")] = None,
    type: Annotated[str | None, Query(max_length=40)] = None,  # noqa: A002 (query name)
    region: Annotated[str | None, Query(max_length=40)] = None,
    real_money: bool | None = None,
    esg: bool | None = None,
    sort: Annotated[str, Query(pattern="^(" + "|".join(SORT_KEYS) + ")$")] = "name",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 25,
) -> InvestorPage:
    """The investor directory with filters, sorting and paging."""
    return await service.directory(
        q=q,
        type_=type,
        region=region,
        real_money=real_money,
        esg=esg,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/investors/{investor_id}", response_model=InvestorProfile)
async def get_investor(investor_id: str, service: Service, _user: CanRead) -> InvestorProfile:
    """One investor: facts, activity across deals and similar investors."""
    return await service.profile(investor_id)


@router.get("/deals/{deal_id}/investor-network", response_model=DealNetwork)
async def investor_network(deal_id: str, service: Service, _user: CanRead) -> DealNetwork:
    """Who is in this deal's book, with roll-ups by type and region."""
    return await service.network(deal_id)


@router.get("/deals/{deal_id}/investor-targets", response_model=list[Target])
async def investor_targets(
    deal_id: str,
    service: Service,
    _user: CanRead,
    limit: Annotated[int, Query(ge=1, le=50)] = 15,
) -> list[Target]:
    """Investors not yet in the book, ranked by an explainable fit score."""
    return await service.targets(deal_id, limit)
