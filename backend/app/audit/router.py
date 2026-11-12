"""Audit endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.audit.models import AuditEvent
from app.audit.service import AuditService
from app.core.security import CurrentUser, Role, require_roles
from app.deps import get_audit_service

router = APIRouter(tags=["audit"])


@router.get("/audit", response_model=list[AuditEvent])
async def list_audit(
    service: Annotated[AuditService, Depends(get_audit_service)],
    _user: Annotated[CurrentUser, Depends(require_roles(Role.admin))],
    action: Annotated[str | None, Query(max_length=60)] = None,
    deal_id: Annotated[str | None, Query(max_length=60)] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AuditEvent]:
    """Admin only: the audit trail, newest first."""
    return await service.list_events(deal_id=deal_id, action_prefix=action, limit=limit)


@router.get("/deals/{deal_id}/timeline", response_model=list[AuditEvent])
async def deal_timeline(
    deal_id: str,
    service: Annotated[AuditService, Depends(get_audit_service)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[AuditEvent]:
    """Every role may see what happened on a deal (creation, task changes, stage moves)."""
    return await service.list_events(deal_id=deal_id, limit=limit)
