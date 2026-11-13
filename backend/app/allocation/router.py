"""Allocation endpoints: a syndicate user proposes, a different approver approves."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.allocation.models import AllocationResult, Proposal, ProposalSummary, ProposeRequest
from app.allocation.service import AllocationService
from app.core.errors import NotFoundError
from app.core.security import CurrentUser, Role, get_current_user, require_roles
from app.deps import get_allocation_service

router = APIRouter(tags=["allocation"], dependencies=[Depends(get_current_user)])

Service = Annotated[AllocationService, Depends(get_allocation_service)]
CanRead = Annotated[CurrentUser, Depends(require_roles(Role.syndicate, Role.approver))]
CanPropose = Annotated[CurrentUser, Depends(require_roles(Role.syndicate))]
CanApprove = Annotated[CurrentUser, Depends(require_roles(Role.approver))]


@router.get("/deals/{deal_id}/allocation/preview", response_model=AllocationResult)
async def preview_allocation(
    deal_id: str, service: Service, _user: CanRead, final_spread_bp: int | None = None
) -> AllocationResult:
    """Compute an allocation without saving it, so the effect of a spread can be explored."""
    return await service.preview(deal_id, final_spread_bp)


@router.get("/deals/{deal_id}/allocation", response_model=list[ProposalSummary])
async def list_proposals(deal_id: str, service: Service, _user: CanRead) -> list[ProposalSummary]:
    return await service.list(deal_id)


@router.get("/allocation/{proposal_id}", response_model=Proposal)
async def get_proposal(proposal_id: str, service: Service, _user: CanRead) -> Proposal:
    return await service.get(proposal_id)


@router.post("/deals/{deal_id}/allocation/propose", response_model=Proposal, status_code=201)
async def propose_allocation(
    deal_id: str, request: ProposeRequest, service: Service, user: CanPropose
) -> Proposal:
    """Compute and save an allocation with an explanation. A new proposal replaces an open one."""
    return await service.propose(deal_id, request.final_spread_bp, user)


@router.post("/deals/{deal_id}/allocation/approve", response_model=Proposal)
async def approve_allocation(
    deal_id: str, proposal_id: str, service: Service, user: CanApprove
) -> Proposal:
    """Approve a proposal. Refused if the approver is the person who proposed it."""
    proposal = await service.get(proposal_id)
    if proposal.deal_id != deal_id:
        raise NotFoundError(f"Proposal {proposal_id} does not belong to deal {deal_id}.")
    return await service.approve(proposal_id, user)
