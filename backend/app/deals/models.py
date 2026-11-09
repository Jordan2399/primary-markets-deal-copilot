"""Deal domain models (API shapes) and small internal dataclasses."""

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, computed_field

from app.deals.templates import STAGE_COUNT


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"


class Stage(BaseModel):
    code: str
    name: str
    position: int


class Issuer(BaseModel):
    id: str
    name: str
    sector: str
    country: str
    rating_band: str


class Task(BaseModel):
    id: str
    deal_id: str
    key: str
    title: str
    owner_role: str
    due: date | None = None
    status: TaskStatus
    blocking: bool
    stage_code: str
    stage_name: str
    stage_position: int
    depends_on: list[str] = Field(default_factory=list)


class TaskDependency(BaseModel):
    id: str
    title: str
    status: TaskStatus


class TaskDetail(Task):
    dependencies: list[TaskDependency] = Field(default_factory=list)


class DealSummary(BaseModel):
    id: str
    name: str
    issuer_id: str
    issuer_name: str
    currency: str
    size_mm: int
    launch_date: date | None = None
    stage_code: str
    stage_name: str
    stage_position: int
    tasks_total: int
    tasks_done: int
    blockers_open: int  # blocking tasks still open in the CURRENT stage

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_complete(self) -> bool:
        return self.stage_position == STAGE_COUNT and self.tasks_done == self.tasks_total


class Tranche(BaseModel):
    id: str
    tenor_years: int
    format: str
    maturity: date | None = None
    coupon: float | None = None
    isin: str | None = None


class DealDetail(DealSummary):
    tranches: list[Tranche] = Field(default_factory=list)


class CreateDealRequest(BaseModel):
    issuer_id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=3, max_length=120)
    currency: Literal["EUR", "USD", "GBP", "CHF"]
    size_mm: int = Field(ge=50, le=5000, description="Deal size in millions")
    tenor_years: int = Field(ge=1, le=40)
    format: Literal["Reg S", "144A", "Domestic"]
    launch_date: date


class UpdateTaskRequest(BaseModel):
    status: TaskStatus


class LaunchReadiness(BaseModel):
    """Facts the Copilot uses to answer 'what is left before launch?'."""

    deal: DealSummary
    open_tasks: list[Task]
    open_before_launch: int
    blocking_open_before_launch: int
    ready_to_launch: bool


@dataclass(frozen=True)
class NewDeal:
    deal_id: str
    issuer_id: str
    name: str
    currency: str
    size_mm: int
    launch_date: date
    tranche_id: str
    tenor_years: int
    format: str
    maturity: date
    coupon: float | None = None
    isin: str | None = None


@dataclass
class AdvanceOutcome:
    status: Literal["advanced", "blocked", "final", "not_found"]
    from_stage: str | None = None
    to_stage: str | None = None
    blockers: list[Task] = field(default_factory=list)
