"""Allocation proposals: persistence."""

import json
from datetime import datetime
from typing import Any, Protocol

from neo4j import AsyncManagedTransaction

from app.allocation.models import AllocationLine, BandSummary, Proposal, ProposalSummary
from app.audit.models import AuditEvent
from app.audit.repository import write_in_tx
from app.db.neo4j import Neo4jClient, run_in_tx

SUPERSEDE = """
MATCH (:Deal {id: $deal_id})-[:HAS_ALLOCATION]->(p:Allocation {state: 'PROPOSED'})
SET p.state = 'SUPERSEDED'
"""

CREATE = """
MATCH (d:Deal {id: $deal_id})
CREATE (d)-[:HAS_ALLOCATION]->(p:Allocation {
  id: $id, deal_id: $deal_id, state: 'PROPOSED', proposed_by: $proposed_by,
  proposed_at: datetime($proposed_at), final_spread_bp: $final_spread_bp,
  deal_size_k: $deal_size_k, eligible_demand_k: $eligible_demand_k,
  total_allocated_k: $total_allocated_k, status: $status, bands: $bands, lines: $lines,
  explanation: $explanation, explanation_source: $explanation_source})
"""

FIELDS = """
p.id AS id, p.deal_id AS deal_id, p.state AS state, p.proposed_by AS proposed_by,
toString(p.proposed_at) AS proposed_at, p.approved_by AS approved_by,
toString(p.approved_at) AS approved_at, p.final_spread_bp AS final_spread_bp,
p.deal_size_k AS deal_size_k, p.eligible_demand_k AS eligible_demand_k,
p.total_allocated_k AS total_allocated_k, p.status AS status
"""

LIST = f"MATCH (:Deal {{id: $deal_id}})-[:HAS_ALLOCATION]->(p:Allocation) RETURN {FIELDS} ORDER BY p.proposed_at DESC"
GET = (
    f"MATCH (p:Allocation {{id: $id}}) RETURN {FIELDS}, p.bands AS bands, p.lines AS lines, "
    "p.explanation AS explanation, p.explanation_source AS explanation_source"
)

# The state check and the change are one statement, so two approvers cannot both succeed.
APPROVE = """
MATCH (p:Allocation {id: $id, state: 'PROPOSED'})
SET p.state = 'APPROVED', p.approved_by = $approved_by, p.approved_at = datetime($approved_at)
RETURN p.id AS id
"""


def _time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class AllocationRepository(Protocol):
    async def save_proposal(self, proposal: Proposal, event: AuditEvent) -> None: ...
    async def get(self, proposal_id: str) -> Proposal | None: ...
    async def list(self, deal_id: str) -> list[ProposalSummary]: ...
    async def approve(
        self, proposal_id: str, approved_by: str, approved_at: datetime, event: AuditEvent
    ) -> bool: ...


class Neo4jAllocationRepository:
    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def save_proposal(self, proposal: Proposal, event: AuditEvent) -> None:
        params: dict[str, Any] = {
            "id": proposal.id,
            "deal_id": proposal.deal_id,
            "proposed_by": proposal.proposed_by,
            "proposed_at": proposal.proposed_at.isoformat(),
            "final_spread_bp": proposal.final_spread_bp,
            "deal_size_k": proposal.deal_size_k,
            "eligible_demand_k": proposal.eligible_demand_k,
            "total_allocated_k": proposal.total_allocated_k,
            "status": proposal.status,
            "bands": json.dumps([b.model_dump() for b in proposal.bands]),
            "lines": json.dumps([line.model_dump() for line in proposal.lines]),
            "explanation": proposal.explanation,
            "explanation_source": proposal.explanation_source,
        }

        async def work(tx: AsyncManagedTransaction) -> None:
            await run_in_tx(tx, SUPERSEDE, {"deal_id": proposal.deal_id})
            await run_in_tx(tx, CREATE, params)
            await write_in_tx(tx, event)

        await self._db.execute_write(work)

    async def get(self, proposal_id: str) -> Proposal | None:
        rows = await self._db.read(GET, {"id": proposal_id})
        if not rows:
            return None
        r = rows[0]
        return Proposal(
            id=r["id"],
            deal_id=r["deal_id"],
            state=r["state"],
            proposed_by=r["proposed_by"],
            proposed_at=datetime.fromisoformat(r["proposed_at"]),
            approved_by=r["approved_by"],
            approved_at=_time(r["approved_at"]),
            final_spread_bp=r["final_spread_bp"],
            deal_size_k=r["deal_size_k"],
            eligible_demand_k=r["eligible_demand_k"],
            total_allocated_k=r["total_allocated_k"],
            status=r["status"],
            bands=[BandSummary(**b) for b in json.loads(r["bands"])],
            lines=[AllocationLine(**line) for line in json.loads(r["lines"])],
            explanation=r["explanation"],
            explanation_source=r["explanation_source"],
        )

    async def list(self, deal_id: str) -> list[ProposalSummary]:
        rows = await self._db.read(LIST, {"deal_id": deal_id})
        return [
            ProposalSummary(
                id=r["id"],
                deal_id=r["deal_id"],
                state=r["state"],
                final_spread_bp=r["final_spread_bp"],
                total_allocated_k=r["total_allocated_k"],
                deal_size_k=r["deal_size_k"],
                proposed_by=r["proposed_by"],
                proposed_at=datetime.fromisoformat(r["proposed_at"]),
                approved_by=r["approved_by"],
            )
            for r in rows
        ]

    async def approve(
        self, proposal_id: str, approved_by: str, approved_at: datetime, event: AuditEvent
    ) -> bool:
        async def work(tx: AsyncManagedTransaction) -> bool:
            rows = await run_in_tx(
                tx,
                APPROVE,
                {
                    "id": proposal_id,
                    "approved_by": approved_by,
                    "approved_at": approved_at.isoformat(),
                },
            )
            if not rows:
                return False
            await write_in_tx(tx, event)
            return True

        return await self._db.execute_write(work)
