"""Global search for the top bar: deals and (for roles that may see them) investors."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.core.security import CurrentUser, Role, get_current_user
from app.deals.service import DealService
from app.deps import get_deal_service, get_investor_service
from app.investors.service import InvestorService

router = APIRouter(tags=["search"])

# Same rule as the investor pages: viewers never see investor names.
INVESTOR_ROLES = {Role.marketer, Role.syndicate, Role.approver, Role.admin}
LIMIT = 6


class DealHit(BaseModel):
    id: str
    name: str
    issuer: str
    stage: str


class InvestorHit(BaseModel):
    id: str
    name: str
    type: str
    region: str


class SearchResults(BaseModel):
    query: str
    deals: list[DealHit]
    investors: list[InvestorHit]


@router.get("/search", response_model=SearchResults)
async def search(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    deals: Annotated[DealService, Depends(get_deal_service)],
    investors: Annotated[InvestorService, Depends(get_investor_service)],
    q: Annotated[str, Query(min_length=1, max_length=60)],
) -> SearchResults:
    needle = q.strip().lower()
    deal_hits = [
        DealHit(id=d.id, name=d.name, issuer=d.issuer_name, stage=d.stage_name)
        for d in await deals.list_deals()
        if needle in d.id.lower() or needle in d.name.lower() or needle in d.issuer_name.lower()
    ][:LIMIT]
    investor_hits: list[InvestorHit] = []
    if user.role in INVESTOR_ROLES:
        page = await investors.directory(
            q=needle,
            type_=None,
            region=None,
            real_money=None,
            esg=None,
            sort="name",
            page=1,
            page_size=LIMIT,
        )
        investor_hits = [
            InvestorHit(id=i.id, name=i.name, type=i.type, region=i.region) for i in page.items
        ]
    return SearchResults(query=q.strip(), deals=deal_hits, investors=investor_hits)
