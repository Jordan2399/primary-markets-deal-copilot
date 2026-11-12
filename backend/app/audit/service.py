"""Audit service."""

from app.audit.models import AuditEvent
from app.audit.repository import AuditRepository


class AuditService:
    def __init__(self, repo: AuditRepository) -> None:
        self._repo = repo

    async def record(self, event: AuditEvent) -> None:
        await self._repo.write(event)

    async def list_events(
        self, *, deal_id: str | None = None, action_prefix: str | None = None, limit: int = 100
    ) -> list[AuditEvent]:
        return await self._repo.query(
            deal_id=deal_id, action_prefix=action_prefix, limit=max(1, min(limit, 500))
        )
