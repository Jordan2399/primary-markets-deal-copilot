"""Investor reads (Cypher lives here). Read-only: investors are created by the seed."""

import json
from typing import Any, Protocol

from app.db.neo4j import Neo4jClient
from app.investors.models import Investor, InvestorOrder
from app.orderbook.repository import LIST_INVESTORS

# Every order with the deal it belongs to. One query for all investors is fine at this size
# (a dozen deals, a few hundred orders) and keeps the directory to one round trip.
ORDERS = """
MATCH (d:Deal)-[:HAS_ORDER]->(o:Order)-[:PLACED_BY]->(i:Investor)
MATCH (d)-[:IN_STAGE]->(s:Stage)
RETURN i.id AS investor_id, o.id AS order_id, d.id AS deal_id, d.name AS deal_name,
       s.name AS stage_name, d.currency AS currency, d.size_mm AS deal_size_mm,
       o.amount_k AS amount_k, o.limit_bp AS limit_bp, toString(o.placed_at) AS placed_at
ORDER BY o.placed_at, o.id
"""

# Allocation proposals hold their lines as JSON text. Superseded proposals are ignored.
ALLOCATIONS = """
MATCH (d:Deal)-[:HAS_ALLOCATION]->(p:Allocation)
WHERE p.state IN ['APPROVED', 'PROPOSED']
RETURN d.id AS deal_id, p.state AS state, p.lines AS lines, toString(p.proposed_at) AS proposed_at
"""


class InvestorRepository(Protocol):
    async def list_investors(self) -> list[Investor]: ...
    async def list_orders(self) -> list[InvestorOrder]: ...


def allocated_by_order(rows: list[dict[str, Any]]) -> dict[str, int]:
    """Map order id -> allocated amount, using ONE proposal per deal.

    An APPROVED proposal wins over a PROPOSED one; among equals the latest proposal wins.
    """
    chosen: dict[str, dict[str, Any]] = {}
    for row in rows:
        current = chosen.get(row["deal_id"])
        rank = (row["state"] == "APPROVED", row["proposed_at"] or "")
        if current is None or rank > (current["state"] == "APPROVED", current["proposed_at"] or ""):
            chosen[row["deal_id"]] = row
    result: dict[str, int] = {}
    for row in chosen.values():
        for line in json.loads(row["lines"] or "[]"):
            result[line["order_id"]] = int(line["allocated_k"])
    return result


class Neo4jInvestorRepository:
    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def list_investors(self) -> list[Investor]:
        return [Investor(**row) for row in await self._db.read(LIST_INVESTORS)]

    async def list_orders(self) -> list[InvestorOrder]:
        rows = await self._db.read(ORDERS)
        allocated = allocated_by_order(await self._db.read(ALLOCATIONS))
        return [InvestorOrder(**row, allocated_k=allocated.get(row["order_id"])) for row in rows]
