"""Deal persistence: the Repository protocol and its Neo4j implementation.

The service layer only knows the `DealRepository` protocol. Tests use an in-memory fake;
production uses `Neo4jDealRepository`. Each write that changes business state also writes
its audit event inside the same transaction.
"""

from collections.abc import Callable
from typing import Any, Protocol

from neo4j import AsyncManagedTransaction

from app.audit.models import AuditEvent
from app.audit.repository import write_in_tx
from app.db.neo4j import Neo4jClient, run_in_tx
from app.deals.models import (
    AdvanceOutcome,
    DealSummary,
    Issuer,
    NewDeal,
    Stage,
    Task,
    TaskDependency,
    TaskDetail,
    TaskStatus,
    Tranche,
)
from app.deals.templates import NewTask

# --------------------------------------------------------------------------- Cypher

LIST_STAGES = "MATCH (s:Stage) RETURN s.code AS code, s.name AS name, s.position AS position ORDER BY s.position"

LIST_ISSUERS = """
MATCH (i:Issuer)
RETURN i.id AS id, i.name AS name, i.sector AS sector, i.country AS country,
       i.rating_band AS rating_band
ORDER BY i.name
"""

LIST_DEALS = """
MATCH (i:Issuer)-[:MANDATED]->(d:Deal)-[:IN_STAGE]->(s:Stage)
WHERE $deal_id IS NULL OR d.id = $deal_id
OPTIONAL MATCH (d)-[:HAS_TASK]->(t:Task)
WITH d, i, s, collect(t) AS ts
RETURN d.id AS id, d.name AS name, i.id AS issuer_id, i.name AS issuer_name,
       d.currency AS currency, d.size_mm AS size_mm, toString(d.launch_date) AS launch_date,
       s.code AS stage_code, s.name AS stage_name, s.position AS stage_position,
       size(ts) AS tasks_total,
       size([t IN ts WHERE t.status = 'DONE']) AS tasks_done,
       size([t IN ts WHERE t.blocking AND t.status <> 'DONE' AND t.stage_code = s.code]) AS blockers_open
ORDER BY s.position, d.launch_date, d.id
"""

LIST_TRANCHES = """
MATCH (:Deal {id: $deal_id})-[:HAS_TRANCHE]->(tr:Tranche)
RETURN tr.id AS id, tr.tenor_years AS tenor_years, tr.format AS format,
       toString(tr.maturity) AS maturity, tr.coupon AS coupon, tr.isin AS isin
ORDER BY tr.id
"""

_TASK_RETURN = """
RETURN t.id AS id, t.deal_id AS deal_id, t.key AS key, t.title AS title,
       t.owner_role AS owner_role, toString(t.due) AS due, t.status AS status,
       t.blocking AS blocking, s.code AS stage_code, s.name AS stage_name,
       s.position AS stage_position, deps AS depends_on
"""

LIST_TASKS = (
    """
MATCH (:Deal {id: $deal_id})-[:HAS_TASK]->(t:Task)-[:BELONGS_TO]->(s:Stage)
WHERE $stage_code IS NULL OR s.code = $stage_code
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
WITH t, s, collect(dep.id) AS deps
"""
    + _TASK_RETURN
    + "ORDER BY s.position, t.due, t.key"
)

GET_TASK = """
MATCH (t:Task {id: $task_id})-[:BELONGS_TO]->(s:Stage)
OPTIONAL MATCH (t)-[:DEPENDS_ON]->(dep:Task)
WITH t, s, collect(dep.id) AS deps, collect(dep {.id, .title, .status}) AS dependencies
""" + _TASK_RETURN.replace("deps AS depends_on", "deps AS depends_on, dependencies")

ISSUER_EXISTS = "MATCH (i:Issuer {id: $issuer_id}) RETURN i.id AS id"

CREATE_DEAL = """
MATCH (i:Issuer {id: $issuer_id}), (s:Stage {code: $stage_code})
CREATE (d:Deal {
  id: $deal_id, name: $name, currency: $currency, size_mm: $size_mm,
  launch_date: date($launch_date), created_at: datetime()
})
CREATE (i)-[:MANDATED]->(d)
CREATE (d)-[:IN_STAGE]->(s)
CREATE (tr:Tranche {
  id: $tranche_id, tenor_years: $tenor_years, format: $format,
  maturity: date($maturity), coupon: $coupon, isin: $isin
})
CREATE (d)-[:HAS_TRANCHE]->(tr)
RETURN d.id AS id
"""

CREATE_TASKS = """
MATCH (d:Deal {id: $deal_id})
UNWIND $tasks AS row
MATCH (s:Stage {code: row.stage_code})
CREATE (t:Task {
  id: row.id, deal_id: $deal_id, key: row.key, title: row.title, owner_role: row.owner_role,
  due: date(row.due), status: row.status, blocking: row.blocking, stage_code: row.stage_code
})
CREATE (d)-[:HAS_TASK]->(t)
CREATE (t)-[:BELONGS_TO]->(s)
"""

CREATE_DEPENDENCIES = """
UNWIND $deps AS row
MATCH (a:Task {id: row.task_id}), (b:Task {id: row.depends_on})
CREATE (a)-[:DEPENDS_ON]->(b)
"""

UPDATE_TASK_STATUS = """
MATCH (t:Task {id: $task_id})
SET t.status = $status, t.updated_at = datetime()
RETURN t.id AS id
"""

CURRENT_STAGE = """
MATCH (:Deal {id: $deal_id})-[:IN_STAGE]->(cur:Stage)
RETURN cur.code AS code, cur.position AS position
"""

STAGE_AT_POSITION = "MATCH (s:Stage {position: $position}) RETURN s.code AS code"

MOVE_STAGE = """
MATCH (d:Deal {id: $deal_id})-[r:IN_STAGE]->(:Stage)
MATCH (n:Stage {code: $to_code})
DELETE r
CREATE (d)-[:IN_STAGE]->(n)
"""

EventFactory = Callable[[str, str], AuditEvent]  # (from_stage_code, to_stage_code) -> event


def task_rows(tasks: list[NewTask]) -> list[dict[str, Any]]:
    return [
        {
            "id": t.id,
            "key": t.key,
            "stage_code": t.stage_code,
            "title": t.title,
            "owner_role": t.owner_role,
            "due": t.due,
            "blocking": t.blocking,
            "status": t.status,
        }
        for t in tasks
    ]


def deal_params(deal: NewDeal, stage_code: str) -> dict[str, Any]:
    return {
        "deal_id": deal.deal_id,
        "issuer_id": deal.issuer_id,
        "stage_code": stage_code,
        "name": deal.name,
        "currency": deal.currency,
        "size_mm": deal.size_mm,
        "launch_date": deal.launch_date.isoformat(),
        "tranche_id": deal.tranche_id,
        "tenor_years": deal.tenor_years,
        "format": deal.format,
        "maturity": deal.maturity.isoformat(),
        "coupon": deal.coupon,
        "isin": deal.isin,
    }


async def create_deal_in_tx(
    tx: AsyncManagedTransaction,
    deal: NewDeal,
    stage_code: str,
    tasks: list[NewTask],
    deps: list[tuple[str, str]],
) -> bool:
    """Create a deal, its tranche and its tasks. Returns False if the issuer or stage is missing."""
    created = await run_in_tx(tx, CREATE_DEAL, deal_params(deal, stage_code))
    if not created:
        return False
    await run_in_tx(tx, CREATE_TASKS, {"deal_id": deal.deal_id, "tasks": task_rows(tasks)})
    await run_in_tx(
        tx,
        CREATE_DEPENDENCIES,
        {"deps": [{"task_id": a, "depends_on": b} for a, b in deps]},
    )
    return True


# --------------------------------------------------------------------------- protocol


class DealRepository(Protocol):
    async def list_stages(self) -> list[Stage]: ...

    async def list_issuers(self) -> list[Issuer]: ...

    async def list_deals(self, deal_id: str | None = None) -> list[DealSummary]: ...

    async def list_tranches(self, deal_id: str) -> list[Tranche]: ...

    async def list_tasks(self, deal_id: str, stage_code: str | None = None) -> list[Task]: ...

    async def get_task(self, task_id: str) -> TaskDetail | None: ...

    async def issuer_exists(self, issuer_id: str) -> bool: ...

    async def create_deal(
        self,
        deal: NewDeal,
        stage_code: str,
        tasks: list[NewTask],
        deps: list[tuple[str, str]],
        event: AuditEvent,
    ) -> bool: ...

    async def update_task_status(
        self, task_id: str, status: TaskStatus, event: AuditEvent
    ) -> None: ...

    async def advance_stage(self, deal_id: str, make_event: EventFactory) -> AdvanceOutcome: ...


# --------------------------------------------------------------------------- Neo4j


class Neo4jDealRepository:
    def __init__(self, db: Neo4jClient) -> None:
        self._db = db

    async def list_stages(self) -> list[Stage]:
        return [Stage(**r) for r in await self._db.read(LIST_STAGES)]

    async def list_issuers(self) -> list[Issuer]:
        return [Issuer(**r) for r in await self._db.read(LIST_ISSUERS)]

    async def list_deals(self, deal_id: str | None = None) -> list[DealSummary]:
        rows = await self._db.read(LIST_DEALS, {"deal_id": deal_id})
        return [DealSummary(**r) for r in rows]

    async def list_tranches(self, deal_id: str) -> list[Tranche]:
        return [Tranche(**r) for r in await self._db.read(LIST_TRANCHES, {"deal_id": deal_id})]

    async def list_tasks(self, deal_id: str, stage_code: str | None = None) -> list[Task]:
        rows = await self._db.read(LIST_TASKS, {"deal_id": deal_id, "stage_code": stage_code})
        return [Task(**r) for r in rows]

    async def get_task(self, task_id: str) -> TaskDetail | None:
        rows = await self._db.read(GET_TASK, {"task_id": task_id})
        if not rows:
            return None
        row = rows[0]
        return TaskDetail(
            **{k: v for k, v in row.items() if k != "dependencies"},
            dependencies=[TaskDependency(**d) for d in row["dependencies"]],
        )

    async def issuer_exists(self, issuer_id: str) -> bool:
        return bool(await self._db.read(ISSUER_EXISTS, {"issuer_id": issuer_id}))

    async def create_deal(
        self,
        deal: NewDeal,
        stage_code: str,
        tasks: list[NewTask],
        deps: list[tuple[str, str]],
        event: AuditEvent,
    ) -> bool:
        async def work(tx: AsyncManagedTransaction) -> bool:
            if not await create_deal_in_tx(tx, deal, stage_code, tasks, deps):
                return False
            await write_in_tx(tx, event)
            return True

        return await self._db.execute_write(work)

    async def update_task_status(self, task_id: str, status: TaskStatus, event: AuditEvent) -> None:
        async def work(tx: AsyncManagedTransaction) -> None:
            await run_in_tx(tx, UPDATE_TASK_STATUS, {"task_id": task_id, "status": status.value})
            await write_in_tx(tx, event)

        await self._db.execute_write(work)

    async def advance_stage(self, deal_id: str, make_event: EventFactory) -> AdvanceOutcome:
        """Check the blocking tasks and move the deal in ONE transaction (no race in between)."""

        async def work(tx: AsyncManagedTransaction) -> AdvanceOutcome:
            current = await run_in_tx(tx, CURRENT_STAGE, {"deal_id": deal_id})
            if not current:
                return AdvanceOutcome(status="not_found")
            from_code = str(current[0]["code"])
            following = await run_in_tx(
                tx, STAGE_AT_POSITION, {"position": int(current[0]["position"]) + 1}
            )
            if not following:
                return AdvanceOutcome(status="final", from_stage=from_code)
            rows = await run_in_tx(tx, LIST_TASKS, {"deal_id": deal_id, "stage_code": from_code})
            blockers = [
                Task(**r) for r in rows if r["blocking"] and r["status"] != TaskStatus.DONE.value
            ]
            if blockers:
                return AdvanceOutcome(status="blocked", from_stage=from_code, blockers=blockers)
            to_code = str(following[0]["code"])
            await run_in_tx(tx, MOVE_STAGE, {"deal_id": deal_id, "to_code": to_code})
            await write_in_tx(tx, make_event(from_code, to_code))
            return AdvanceOutcome(status="advanced", from_stage=from_code, to_stage=to_code)

        return await self._db.execute_write(work)
