"""In-memory stand-ins for the repositories, so business rules can be tested without Neo4j."""

from datetime import date, datetime, timedelta
from typing import Any

from app.audit.models import AuditEvent, build_event
from app.core.security import CurrentUser, Role
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
from app.deals.repository import EventFactory
from app.deals.templates import (
    STAGE_BY_CODE,
    STAGES,
    NewTask,
    add_years,
    initial_statuses,
    instantiate_tasks,
)
from app.documents.chunking import ChunkSpec
from app.documents.models import ChunkHit, DocumentRecord

ADMIN = CurrentUser(name="tester", role=Role.admin)
MARKETER = CurrentUser(name="mia.marketer", role=Role.marketer)
SYNDICATE = CurrentUser(name="sam.syndicate", role=Role.syndicate)
VIEWER = CurrentUser(name="vera.viewer", role=Role.viewer)


class FakeDealRepository:
    def __init__(self) -> None:
        self.issuers: dict[str, Issuer] = {
            "ISS-001": Issuer(
                id="ISS-001",
                name="Nordvik Energie AG",
                sector="Utilities",
                country="DE",
                rating_band="A-",
            ),
            "ISS-002": Issuer(
                id="ISS-002",
                name="Aurelia Water NV",
                sector="Utilities",
                country="NL",
                rating_band="A+",
            ),
        }
        self.events: list[AuditEvent] = []
        self._deals: dict[str, dict[str, Any]] = {}
        self._tasks: dict[str, Task] = {}
        self._tranches: dict[str, list[Tranche]] = {}

    # ------------------------------------------------------------------ reads
    async def list_stages(self) -> list[Stage]:
        return [Stage(code=s.code, name=s.name, position=s.position) for s in STAGES]

    async def list_issuers(self) -> list[Issuer]:
        return list(self.issuers.values())

    def _summary(self, deal_id: str) -> DealSummary:
        d = self._deals[deal_id]
        issuer = self.issuers[d["issuer_id"]]
        stage = STAGE_BY_CODE[d["stage_code"]]
        tasks = [t for t in self._tasks.values() if t.deal_id == deal_id]
        return DealSummary(
            id=deal_id,
            name=d["name"],
            issuer_id=issuer.id,
            issuer_name=issuer.name,
            currency=d["currency"],
            size_mm=d["size_mm"],
            launch_date=d["launch_date"],
            stage_code=stage.code,
            stage_name=stage.name,
            stage_position=stage.position,
            tasks_total=len(tasks),
            tasks_done=sum(1 for t in tasks if t.status is TaskStatus.DONE),
            blockers_open=sum(
                1
                for t in tasks
                if t.blocking and t.status is not TaskStatus.DONE and t.stage_code == stage.code
            ),
        )

    async def list_deals(self, deal_id: str | None = None) -> list[DealSummary]:
        ids = [deal_id] if deal_id else list(self._deals)
        return [self._summary(i) for i in ids if i in self._deals]

    async def list_tranches(self, deal_id: str) -> list[Tranche]:
        return self._tranches.get(deal_id, [])

    async def list_tasks(self, deal_id: str, stage_code: str | None = None) -> list[Task]:
        tasks = [
            t
            for t in self._tasks.values()
            if t.deal_id == deal_id and (stage_code is None or t.stage_code == stage_code)
        ]
        return sorted(tasks, key=lambda t: (t.stage_position, t.due or date.min, t.key))

    async def get_task(self, task_id: str) -> TaskDetail | None:
        task = self._tasks.get(task_id)
        if task is None:
            return None
        deps = [
            TaskDependency(id=d.id, title=d.title, status=d.status)
            for d in (self._tasks[i] for i in task.depends_on)
        ]
        return TaskDetail(**task.model_dump(), dependencies=deps)

    async def issuer_exists(self, issuer_id: str) -> bool:
        return issuer_id in self.issuers

    # ------------------------------------------------------------------ writes
    async def create_deal(
        self,
        deal: NewDeal,
        stage_code: str,
        tasks: list[NewTask],
        deps: list[tuple[str, str]],
        event: AuditEvent,
    ) -> bool:
        if deal.issuer_id not in self.issuers:
            return False
        self._deals[deal.deal_id] = {
            "issuer_id": deal.issuer_id,
            "name": deal.name,
            "currency": deal.currency,
            "size_mm": deal.size_mm,
            "launch_date": deal.launch_date,
            "stage_code": stage_code,
        }
        self._tranches[deal.deal_id] = [
            Tranche(
                id=deal.tranche_id,
                tenor_years=deal.tenor_years,
                format=deal.format,
                maturity=deal.maturity,
                coupon=deal.coupon,
                isin=deal.isin,
            )
        ]
        for nt in tasks:
            stage = STAGE_BY_CODE[nt.stage_code]
            self._tasks[nt.id] = Task(
                id=nt.id,
                deal_id=deal.deal_id,
                key=nt.key,
                title=nt.title,
                owner_role=nt.owner_role,
                due=date.fromisoformat(nt.due),
                status=TaskStatus(nt.status),
                blocking=nt.blocking,
                stage_code=nt.stage_code,
                stage_name=stage.name,
                stage_position=stage.position,
                depends_on=[b for a, b in deps if a == nt.id],
            )
        self.events.append(event)
        return True

    async def update_task_status(self, task_id: str, status: TaskStatus, event: AuditEvent) -> None:
        self._tasks[task_id] = self._tasks[task_id].model_copy(update={"status": status})
        self.events.append(event)

    async def advance_stage(self, deal_id: str, make_event: EventFactory) -> AdvanceOutcome:
        if deal_id not in self._deals:
            return AdvanceOutcome(status="not_found")
        current = STAGE_BY_CODE[self._deals[deal_id]["stage_code"]]
        following = next((s for s in STAGES if s.position == current.position + 1), None)
        if following is None:
            return AdvanceOutcome(status="final", from_stage=current.code)
        blockers = [
            t
            for t in await self.list_tasks(deal_id, current.code)
            if t.blocking and t.status is not TaskStatus.DONE
        ]
        if blockers:
            return AdvanceOutcome(status="blocked", from_stage=current.code, blockers=blockers)
        self._deals[deal_id]["stage_code"] = following.code
        self.events.append(make_event(current.code, following.code))
        return AdvanceOutcome(status="advanced", from_stage=current.code, to_stage=following.code)


async def add_deal(
    repo: FakeDealRepository,
    deal_id: str = "D-DEMO-001",
    stage_code: str = "documentation",
    done_in_stage: int = 2,
    launch: date | None = None,
    issuer_id: str = "ISS-001",
) -> None:
    """Put a deal part-way through the process, like the seed does."""
    launch = launch or date.today() + timedelta(days=14)
    deal = NewDeal(
        deal_id=deal_id,
        issuer_id=issuer_id,
        name="Nordvik EUR 750m 5Y",
        currency="EUR",
        size_mm=750,
        launch_date=launch,
        tranche_id=f"{deal_id}-T1",
        tenor_years=5,
        format="Reg S",
        maturity=add_years(launch, 5),
    )
    tasks, deps = instantiate_tasks(deal_id, launch, initial_statuses(stage_code, done_in_stage))
    event = build_event(ADMIN, "deal.create", "deal", deal_id, deal_id=deal_id)
    assert await repo.create_deal(deal, stage_code, tasks, deps, event)


class FakeAuditRepository:
    """Shares the event list of a FakeDealRepository so the timeline can be tested."""

    def __init__(self, events: list[AuditEvent] | None = None) -> None:
        self.events: list[AuditEvent] = events if events is not None else []

    async def write(self, event: AuditEvent) -> None:
        self.events.append(event)

    async def query(
        self, *, deal_id: str | None, action_prefix: str | None, limit: int
    ) -> list[AuditEvent]:
        found = [
            e
            for e in reversed(self.events)
            if (deal_id is None or e.deal_id == deal_id)
            and (action_prefix is None or e.action.startswith(action_prefix))
        ]
        return found[:limit]


class InMemoryDocumentRepository:
    """Stores chunk vectors and ranks by cosine similarity, like the Neo4j vector index does."""

    def __init__(self) -> None:
        self.chunks: dict[str, tuple[ChunkSpec, list[float], DocumentRecord]] = {}

    async def replace_document(
        self, record: DocumentRecord, chunks: list[ChunkSpec], embeddings: list[list[float]]
    ) -> None:
        for chunk_id in [k for k, v in self.chunks.items() if v[2].id == record.id]:
            del self.chunks[chunk_id]
        for chunk, vector in zip(chunks, embeddings, strict=True):
            self.chunks[chunk.id] = (chunk, vector, record)

    async def search(self, embedding: list[float], k: int) -> list[ChunkHit]:
        scored = []
        for chunk, vector, record in self.chunks.values():
            cosine = sum(a * b for a, b in zip(embedding, vector, strict=True))
            scored.append(
                ChunkHit(
                    chunk_id=chunk.id,
                    doc_id=record.id,
                    doc_title=record.title,
                    heading=chunk.heading,
                    text=chunk.text,
                    score=(1 + cosine) / 2,
                )
            )
        return sorted(scored, key=lambda h: h.score, reverse=True)[:k]

    async def count_chunks(self) -> int:
        return len(self.chunks)


def parse_sse(body: str) -> list[tuple[str, dict[str, Any]]]:
    """Parse a server-sent-events body into (event, data) pairs."""
    import json

    events: list[tuple[str, dict[str, Any]]] = []
    for block in body.strip().split("\n\n"):
        name = ""
        data = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                name = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if name:
            events.append((name, json.loads(data)))
    return events


# ---------------------------------------------------------------- Day 2 fakes
from app.allocation.models import Proposal, ProposalSummary  # noqa: E402
from app.investors.generator import build_investors  # noqa: E402
from app.investors.models import Investor  # noqa: E402
from app.orderbook.models import BookParams, NewOrder, OrderRow  # noqa: E402
from app.termsheets.models import StoredTermSheet  # noqa: E402


class FakeOrderBookRepository:
    def __init__(self, events: list[AuditEvent], investors: list[Investor] | None = None) -> None:
        self.events = events
        self.investors = investors if investors is not None else build_investors()
        self._params: dict[str, BookParams] = {}
        self._orders: dict[str, list[NewOrder]] = {}

    async def upsert_investors(self, investors: list[Investor]) -> None:
        self.investors = investors

    async def list_investors(self) -> list[Investor]:
        return self.investors

    async def get_params(self, deal_id: str) -> BookParams | None:
        return self._params.get(deal_id)

    async def list_orders(self, deal_id: str) -> list[OrderRow]:
        by_id = {i.id: i for i in self.investors}
        rows = []
        for o in sorted(self._orders.get(deal_id, []), key=lambda x: (x.placed_at, x.id)):
            inv = by_id[o.investor_id]
            rows.append(
                OrderRow(
                    id=o.id,
                    investor_id=inv.id,
                    investor_name=inv.name,
                    investor_type=inv.type,
                    region=inv.region,
                    real_money=inv.real_money,
                    ticket_mean_k=inv.ticket_mean_k,
                    ticket_std_k=inv.ticket_std_k,
                    past_participation=inv.past_participation,
                    amount_k=o.amount_k,
                    limit_bp=o.limit_bp,
                    placed_at=o.placed_at,
                )
            )
        return rows

    async def count_orders(self, deal_id: str) -> int:
        return len(self._orders.get(deal_id, []))

    async def save_book(
        self,
        deal_id: str,
        params: BookParams,
        orders: list[NewOrder],
        *,
        replace: bool,
        event: AuditEvent,
    ) -> None:
        self._params[deal_id] = params
        self._orders[deal_id] = (
            list(orders) if replace else [*self._orders.get(deal_id, []), *orders]
        )
        self.events.append(event)


class FakeAllocationRepository:
    def __init__(self, events: list[AuditEvent]) -> None:
        self.events = events
        self.proposals: dict[str, Proposal] = {}

    async def save_proposal(self, proposal: Proposal, event: AuditEvent) -> None:
        for key, existing in list(self.proposals.items()):
            if existing.deal_id == proposal.deal_id and existing.state == "PROPOSED":
                self.proposals[key] = existing.model_copy(update={"state": "SUPERSEDED"})
        self.proposals[proposal.id] = proposal
        self.events.append(event)

    async def get(self, proposal_id: str) -> Proposal | None:
        return self.proposals.get(proposal_id)

    async def list(self, deal_id: str) -> list[ProposalSummary]:
        return [
            ProposalSummary(**p.model_dump(include=set(ProposalSummary.model_fields)))
            for p in sorted(self.proposals.values(), key=lambda p: p.proposed_at, reverse=True)
            if p.deal_id == deal_id
        ]

    async def approve(
        self, proposal_id: str, approved_by: str, approved_at: datetime, event: AuditEvent
    ) -> bool:
        current = self.proposals.get(proposal_id)
        if current is None or current.state != "PROPOSED":
            return False
        self.proposals[proposal_id] = current.model_copy(
            update={"state": "APPROVED", "approved_by": approved_by, "approved_at": approved_at}
        )
        self.events.append(event)
        return True


class FakeTermSheetRepository:
    def __init__(self, events: list[AuditEvent]) -> None:
        self.events = events
        self.docs: dict[str, StoredTermSheet] = {}

    async def save(self, doc: StoredTermSheet, event: AuditEvent) -> None:
        self.docs[doc.id] = doc
        self.events.append(event)

    async def get(self, doc_id: str) -> StoredTermSheet | None:
        return self.docs.get(doc_id)


class FakeUserRepository:
    def __init__(self, users: list[Any] | None = None) -> None:
        self.users: dict[str, Any] = {u.username: u for u in (users or [])}

    async def get(self, username: str) -> Any:
        return self.users.get(username)

    async def all_users(self) -> list[Any]:
        return sorted(self.users.values(), key=lambda u: u.username)

    async def create_if_missing(self, user: Any) -> bool:
        if user.username in self.users:
            return False
        self.users[user.username] = user
        return True


class FakeConversationRepository:
    """Same ownership rules as the Neo4j version: every lookup is by id AND owner."""

    def __init__(self, events: list[AuditEvent] | None = None) -> None:
        self.events: list[AuditEvent] = events if events is not None else []
        self.threads: dict[str, dict[str, Any]] = {}
        self.clock = 0

    def _tick(self) -> str:
        self.clock += 1
        return f"2026-11-12T10:00:{self.clock:02d}+00:00"

    def _summary(self, t: dict[str, Any]) -> Any:
        from app.conversations.models import ConversationSummary

        return ConversationSummary(
            id=t["id"],
            title=t["title"],
            deal_id=t["deal_id"],
            created_at=t["created_at"],
            updated_at=t["updated_at"],
            message_count=len(t["messages"]),
        )

    async def list_owned(self, owner: str, limit: int) -> list[Any]:
        mine = [t for t in self.threads.values() if t["owner"] == owner]
        mine.sort(key=lambda t: t["updated_at"], reverse=True)
        return [self._summary(t) for t in mine[:limit]]

    async def get(self, conversation_id: str, owner: str) -> Any:
        from app.conversations.models import ConversationDetail

        t = self.threads.get(conversation_id)
        if t is None or t["owner"] != owner:
            return None
        return ConversationDetail(**self._summary(t).model_dump(), messages=list(t["messages"]))

    async def recent_messages(self, conversation_id: str, owner: str, limit: int) -> list[Any]:
        t = self.threads.get(conversation_id)
        if t is None or t["owner"] != owner:
            return []
        return list(t["messages"])[-limit:]

    async def append_turn(
        self, conversation_id: str, owner: str, deal_id: str | None, title: str, messages: list[Any]
    ) -> bool:
        t = self.threads.get(conversation_id)
        if t is None:
            now = self._tick()
            t = {
                "id": conversation_id,
                "owner": owner,
                "title": title,
                "deal_id": deal_id,
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }
            self.threads[conversation_id] = t
        elif t["owner"] != owner:
            return False
        t["deal_id"] = deal_id
        t["updated_at"] = self._tick()
        for m in messages:
            t["messages"].append(m.model_copy(update={"created_at": t["updated_at"]}))
        return True

    async def rename(self, conversation_id: str, owner: str, title: str) -> bool:
        t = self.threads.get(conversation_id)
        if t is None or t["owner"] != owner:
            return False
        t["title"] = title
        return True

    async def delete(self, conversation_id: str, owner: str, event: AuditEvent) -> bool:
        t = self.threads.get(conversation_id)
        if t is None or t["owner"] != owner:
            return False
        del self.threads[conversation_id]
        self.events.append(event)
        return True
