"""Order book persistence (Cypher lives here)."""

from datetime import datetime
from typing import Any, Protocol

from neo4j import AsyncManagedTransaction

from app.audit.models import AuditEvent
from app.audit.repository import write_in_tx
from app.db.neo4j import Neo4jClient, run_in_tx
from app.investors.models import Investor
from app.orderbook.models import BookParams, NewOrder, OrderRow

UPSERT_INVESTORS = """
UNWIND $rows AS r
MERGE (i:Investor {id: r.id})
SET i.name = r.name, i.type = r.type, i.region = r.region, i.real_money = r.real_money,
    i.esg_focus = r.esg_focus, i.ticket_mean_k = r.ticket_mean_k, i.ticket_std_k = r.ticket_std_k,
    i.past_participation = r.past_participation, i.synthetic = true
"""

LIST_INVESTORS = """
MATCH (i:Investor)
RETURN i.id AS id, i.name AS name, i.type AS type, i.region AS region,
       i.real_money AS real_money, i.esg_focus AS esg_focus, i.ticket_mean_k AS ticket_mean_k,
       i.ticket_std_k AS ticket_std_k, i.past_participation AS past_participation
ORDER BY i.id
"""

GET_PARAMS = """
MATCH (d:Deal {id: $deal_id})
WHERE d.book_open IS NOT NULL
RETURN toString(d.book_open) AS open_at, toString(d.book_close) AS close_at, d.ipt_bp AS ipt_bp
"""

LIST_ORDERS = """
MATCH (:Deal {id: $deal_id})-[:HAS_ORDER]->(o:Order)-[:PLACED_BY]->(i:Investor)
RETURN o.id AS id, i.id AS investor_id, i.name AS investor_name, i.type AS investor_type,
       i.region AS region, i.real_money AS real_money, i.ticket_mean_k AS ticket_mean_k,
       i.ticket_std_k AS ticket_std_k, i.past_participation AS past_participation,
       o.amount_k AS amount_k, o.limit_bp AS limit_bp, toString(o.placed_at) AS placed_at
ORDER BY o.placed_at, o.id
"""

DELETE_ORDERS = "MATCH (:Deal {id: $deal_id})-[:HAS_ORDER]->(o:Order) DETACH DELETE o"

SET_PARAMS = """
MATCH (d:Deal {id: $deal_id})
SET d.book_open = datetime($open_at), d.book_close = datetime($close_at), d.ipt_bp = $ipt_bp
"""

CREATE_ORDERS = """
UNWIND $orders AS o
MATCH (d:Deal {id: $deal_id}), (i:Investor {id: o.investor_id})
CREATE (d)-[:HAS_ORDER]->(n:Order {
  id: o.id, deal_id: $deal_id, amount_k: o.amount_k, limit_bp: o.limit_bp,
  placed_at: datetime(o.placed_at)})
CREATE (n)-[:PLACED_BY]->(i)
"""

COUNT_ORDERS = "MATCH (:Deal {id: $deal_id})-[:HAS_ORDER]->(o:Order) RETURN count(o) AS n"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


class OrderBookRepository(Protocol):
    async def upsert_investors(self, investors: list[Investor]) -> None: ...
    async def list_investors(self) -> list[Investor]: ...
    async def get_params(self, deal_id: str) -> BookParams | None: ...
    async def list_orders(self, deal_id: str) -> list[OrderRow]: ...
    async def count_orders(self, deal_id: str) -> int: ...
    async def save_book(
        self,
        deal_id: str,
        params: BookParams,
        orders: list[NewOrder],
        *,
        replace: bool,
        event: AuditEvent,
    ) -> None: ...


class Neo4jOrderBookRepository:
    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def upsert_investors(self, investors: list[Investor]) -> None:
        await self._db.write(UPSERT_INVESTORS, {"rows": [i.model_dump() for i in investors]})

    async def list_investors(self) -> list[Investor]:
        return [Investor(**r) for r in await self._db.read(LIST_INVESTORS)]

    async def get_params(self, deal_id: str) -> BookParams | None:
        rows = await self._db.read(GET_PARAMS, {"deal_id": deal_id})
        if not rows:
            return None
        row = rows[0]
        return BookParams(
            open_at=parse_time(row["open_at"]),
            close_at=parse_time(row["close_at"]),
            ipt_bp=int(row["ipt_bp"]),
        )

    async def list_orders(self, deal_id: str) -> list[OrderRow]:
        rows = await self._db.read(LIST_ORDERS, {"deal_id": deal_id})
        return [OrderRow(**{**r, "placed_at": parse_time(r["placed_at"])}) for r in rows]

    async def count_orders(self, deal_id: str) -> int:
        rows = await self._db.read(COUNT_ORDERS, {"deal_id": deal_id})
        return int(rows[0]["n"]) if rows else 0

    async def save_book(
        self,
        deal_id: str,
        params: BookParams,
        orders: list[NewOrder],
        *,
        replace: bool,
        event: AuditEvent,
    ) -> None:
        payload: list[dict[str, Any]] = [
            {**o.model_dump(), "placed_at": o.placed_at.isoformat()} for o in orders
        ]

        async def work(tx: AsyncManagedTransaction) -> None:
            if replace:
                await run_in_tx(tx, DELETE_ORDERS, {"deal_id": deal_id})
            await run_in_tx(
                tx,
                SET_PARAMS,
                {
                    "deal_id": deal_id,
                    "open_at": params.open_at.isoformat(),
                    "close_at": params.close_at.isoformat(),
                    "ipt_bp": params.ipt_bp,
                },
            )
            await run_in_tx(tx, CREATE_ORDERS, {"deal_id": deal_id, "orders": payload})
            await write_in_tx(tx, event)

        await self._db.execute_write(work)
