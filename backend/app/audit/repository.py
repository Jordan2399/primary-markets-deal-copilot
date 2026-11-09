"""Audit persistence.

`write_in_tx` is the important function: other modules call it inside their own write
transaction, so a business change and its audit record are saved together or not at all.
AuditEvent nodes are only ever created, never updated or deleted by this code. (The database
itself does not enforce that; a real deployment would add that control.)
"""

import json
from typing import Any, Protocol

from neo4j import AsyncManagedTransaction

from app.audit.models import AuditEvent
from app.db.neo4j import Neo4jClient, run_in_tx

CREATE_AUDIT = """
CREATE (a:AuditEvent {
  id: $id, ts: datetime($ts), actor: $actor, role: $role, action: $action,
  entity_type: $entity_type, entity_id: $entity_id, deal_id: $deal_id,
  details: $details, model: $model, prompt_hash: $prompt_hash, sources: $sources
})
"""

QUERY_AUDIT = """
MATCH (a:AuditEvent)
WHERE ($deal_id IS NULL OR a.deal_id = $deal_id)
  AND ($action IS NULL OR a.action STARTS WITH $action)
RETURN a.id AS id, toString(a.ts) AS ts, a.actor AS actor, a.role AS role, a.action AS action,
       a.entity_type AS entity_type, a.entity_id AS entity_id, a.deal_id AS deal_id,
       a.details AS details, a.model AS model, a.prompt_hash AS prompt_hash,
       a.sources AS sources
ORDER BY a.ts DESC
LIMIT $limit
"""


def audit_params(event: AuditEvent) -> dict[str, Any]:
    return {
        "id": event.id,
        "ts": event.ts,
        "actor": event.actor,
        "role": event.role,
        "action": event.action,
        "entity_type": event.entity_type,
        "entity_id": event.entity_id,
        "deal_id": event.deal_id,
        "details": json.dumps(event.details, default=str),
        "model": event.model,
        "prompt_hash": event.prompt_hash,
        "sources": event.sources,
    }


async def write_in_tx(tx: AsyncManagedTransaction, event: AuditEvent) -> None:
    await run_in_tx(tx, CREATE_AUDIT, audit_params(event))


def _row_to_event(row: dict[str, Any]) -> AuditEvent:
    try:
        details = json.loads(row.get("details") or "{}")
    except json.JSONDecodeError:
        details = {}
    return AuditEvent(**{**row, "details": details, "sources": row.get("sources") or []})


class AuditRepository(Protocol):
    async def write(self, event: AuditEvent) -> None: ...

    async def query(
        self, *, deal_id: str | None, action_prefix: str | None, limit: int
    ) -> list[AuditEvent]: ...


class Neo4jAuditRepository:
    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def write(self, event: AuditEvent) -> None:
        await self._db.write(CREATE_AUDIT, audit_params(event))

    async def query(
        self, *, deal_id: str | None, action_prefix: str | None, limit: int
    ) -> list[AuditEvent]:
        rows = await self._db.read(
            QUERY_AUDIT, {"deal_id": deal_id, "action": action_prefix, "limit": limit}
        )
        return [_row_to_event(r) for r in rows]
