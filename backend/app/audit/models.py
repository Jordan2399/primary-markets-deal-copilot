"""Audit events: who did what, when, and (for AI calls) with which model and sources."""

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.security import CurrentUser


class AuditEvent(BaseModel):
    id: str
    ts: str
    actor: str
    role: str
    action: str
    entity_type: str
    entity_id: str
    deal_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    prompt_hash: str | None = None
    sources: list[str] = Field(default_factory=list)


def build_event(
    user: CurrentUser,
    action: str,
    entity_type: str,
    entity_id: str,
    *,
    deal_id: str | None = None,
    details: dict[str, Any] | None = None,
    model: str | None = None,
    prompt_hash: str | None = None,
    sources: list[str] | None = None,
) -> AuditEvent:
    return AuditEvent(
        id=uuid.uuid4().hex,
        ts=datetime.now(UTC).isoformat(),
        actor=user.name,
        role=user.role.value,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        deal_id=deal_id,
        details=details or {},
        model=model,
        prompt_hash=prompt_hash,
        sources=sources or [],
    )
