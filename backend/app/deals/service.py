"""Deal business rules.

Rules enforced here (and covered by tests):
- A deal is created at the first stage with the full task checklist.
- A task cannot be marked DONE while a task it depends on is not DONE.
- A deal can only move to the next stage when every BLOCKING task of its current stage is DONE.
- Every change writes an audit event.
"""

import uuid
from collections.abc import Callable
from datetime import date

from app.audit.models import build_event
from app.core.errors import ConflictError, NotFoundError
from app.core.security import CurrentUser
from app.deals.models import (
    CreateDealRequest,
    DealDetail,
    DealSummary,
    Issuer,
    LaunchReadiness,
    NewDeal,
    Stage,
    Task,
    TaskStatus,
)
from app.deals.repository import DealRepository
from app.deals.templates import FIRST_STAGE, LAUNCH_POSITION, add_years, instantiate_tasks


class DealService:
    def __init__(self, repo: DealRepository, *, today: Callable[[], date] = date.today) -> None:
        self._repo = repo
        self._today = today

    # ------------------------------------------------------------------ reads

    async def list_stages(self) -> list[Stage]:
        return await self._repo.list_stages()

    async def list_issuers(self) -> list[Issuer]:
        return await self._repo.list_issuers()

    async def list_deals(self) -> list[DealSummary]:
        return await self._repo.list_deals()

    async def _summary(self, deal_id: str) -> DealSummary:
        found = await self._repo.list_deals(deal_id)
        if not found:
            raise NotFoundError(f"Deal '{deal_id}' does not exist.")
        return found[0]

    async def get_deal(self, deal_id: str) -> DealDetail:
        summary = await self._summary(deal_id)
        tranches = await self._repo.list_tranches(deal_id)
        return DealDetail(**summary.model_dump(exclude={"is_complete"}), tranches=tranches)

    async def list_tasks(self, deal_id: str) -> list[Task]:
        await self._summary(deal_id)  # raises 404 for an unknown deal
        return await self._repo.list_tasks(deal_id)

    async def launch_readiness(self, deal_id: str) -> LaunchReadiness:
        """Deterministic facts for 'what is left before launch?'. The LLM only phrases them."""
        deal = await self._summary(deal_id)
        tasks = await self._repo.list_tasks(deal_id)
        open_tasks = [t for t in tasks if t.status != TaskStatus.DONE]
        before = [t for t in open_tasks if t.stage_position <= LAUNCH_POSITION]
        blocking_before = [t for t in before if t.blocking]
        blocking_pre_launch_stages = [
            t for t in blocking_before if t.stage_position < LAUNCH_POSITION
        ]
        return LaunchReadiness(
            deal=deal,
            open_tasks=open_tasks,
            open_before_launch=len(before),
            blocking_open_before_launch=len(blocking_before),
            ready_to_launch=not blocking_pre_launch_stages,
        )

    # ------------------------------------------------------------------ writes

    async def create_deal(self, request: CreateDealRequest, user: CurrentUser) -> DealDetail:
        if request.launch_date < self._today():
            raise ConflictError("The launch date cannot be in the past.")
        if not await self._repo.issuer_exists(request.issuer_id):
            raise NotFoundError(f"Issuer '{request.issuer_id}' does not exist.")

        deal_id = f"D-{request.launch_date.year}-{uuid.uuid4().hex[:5].upper()}"
        deal = NewDeal(
            deal_id=deal_id,
            issuer_id=request.issuer_id,
            name=request.name.strip(),
            currency=request.currency,
            size_mm=request.size_mm,
            launch_date=request.launch_date,
            tranche_id=f"{deal_id}-T1",
            tenor_years=request.tenor_years,
            format=request.format,
            maturity=add_years(request.launch_date, request.tenor_years),
        )
        tasks, deps = instantiate_tasks(deal_id, request.launch_date)
        event = build_event(
            user,
            "deal.create",
            "deal",
            deal_id,
            deal_id=deal_id,
            details={"name": deal.name, "tasks_created": len(tasks), "issuer_id": deal.issuer_id},
        )
        if not await self._repo.create_deal(deal, FIRST_STAGE, tasks, deps, event):
            raise NotFoundError(
                "The issuer or the first stage is missing. Has the database been seeded?"
            )
        return await self.get_deal(deal_id)

    async def update_task(self, task_id: str, status: TaskStatus, user: CurrentUser) -> Task:
        task = await self._repo.get_task(task_id)
        if task is None:
            raise NotFoundError(f"Task '{task_id}' does not exist.")

        if status is TaskStatus.DONE:
            unfinished = [d for d in task.dependencies if d.status is not TaskStatus.DONE]
            if unfinished:
                raise ConflictError(
                    "This task depends on tasks that are not done yet.",
                    details={"open_dependencies": [d.model_dump(mode="json") for d in unfinished]},
                )

        if task.status is not status:
            event = build_event(
                user,
                "task.update",
                "task",
                task.id,
                deal_id=task.deal_id,
                details={"title": task.title, "from": task.status.value, "to": status.value},
            )
            await self._repo.update_task_status(task.id, status, event)

        updated = [t for t in await self._repo.list_tasks(task.deal_id) if t.id == task.id]
        return updated[0]

    async def advance(self, deal_id: str, user: CurrentUser) -> DealSummary:
        def make_event(from_code: str, to_code: str):  # type: ignore[no-untyped-def]
            return build_event(
                user,
                "deal.advance",
                "deal",
                deal_id,
                deal_id=deal_id,
                details={"from": from_code, "to": to_code},
            )

        outcome = await self._repo.advance_stage(deal_id, make_event)
        if outcome.status == "not_found":
            raise NotFoundError(f"Deal '{deal_id}' does not exist.")
        if outcome.status == "final":
            raise ConflictError("The deal is already in the last stage.")
        if outcome.status == "blocked":
            raise ConflictError(
                "Blocking tasks are still open in the current stage.",
                details={"blockers": [t.model_dump(mode="json") for t in outcome.blockers]},
            )
        return await self._summary(deal_id)
