"""Deal endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, Role, require_roles
from app.deals.models import (
    CreateDealRequest,
    DealDetail,
    DealSummary,
    Issuer,
    Stage,
    Task,
    UpdateTaskRequest,
)
from app.deals.service import DealService
from app.deps import get_deal_service

router = APIRouter(tags=["deals"])

Service = Annotated[DealService, Depends(get_deal_service)]
CanEdit = Annotated[CurrentUser, Depends(require_roles(Role.marketer, Role.syndicate))]
CanCreate = Annotated[CurrentUser, Depends(require_roles(Role.marketer))]


@router.get("/stages", response_model=list[Stage])
async def list_stages(service: Service) -> list[Stage]:
    return await service.list_stages()


@router.get("/issuers", response_model=list[Issuer])
async def list_issuers(service: Service) -> list[Issuer]:
    return await service.list_issuers()


@router.get("/deals", response_model=list[DealSummary])
async def list_deals(service: Service) -> list[DealSummary]:
    return await service.list_deals()


@router.post("/deals", response_model=DealDetail, status_code=201)
async def create_deal(request: CreateDealRequest, service: Service, user: CanCreate) -> DealDetail:
    """Create a deal at the Mandate stage with the full task checklist."""
    return await service.create_deal(request, user)


@router.get("/deals/{deal_id}", response_model=DealDetail)
async def get_deal(deal_id: str, service: Service) -> DealDetail:
    return await service.get_deal(deal_id)


@router.get("/deals/{deal_id}/tasks", response_model=list[Task])
async def list_tasks(deal_id: str, service: Service) -> list[Task]:
    """All tasks of the deal, ordered by stage and due date."""
    return await service.list_tasks(deal_id)


@router.patch("/tasks/{task_id}", response_model=Task)
async def update_task(
    task_id: str, request: UpdateTaskRequest, service: Service, user: CanEdit
) -> Task:
    return await service.update_task(task_id, request.status, user)


@router.post("/deals/{deal_id}/advance", response_model=DealSummary)
async def advance_deal(deal_id: str, service: Service, user: CanEdit) -> DealSummary:
    """Move to the next stage. Returns 409 with the blocking tasks if the stage is not finished."""
    return await service.advance(deal_id, user)
