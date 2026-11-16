"""Shapes of the reports page. Every number is computed on the server from the stored data."""

from pydantic import BaseModel, Field


class Kpis(BaseModel):
    active_deals: int  # deals that are not complete
    in_market: int  # active deals at book building or later
    completed_deals: int
    orders: int
    investors_active: int  # investors with at least one order
    avg_cover: float | None  # average cover of deals that have a book; None when there is none
    pending_approvals: int  # allocation proposals waiting for a second pair of eyes
    blocking_tasks: int  # blocking tasks open in the current stage of active deals


class StageRow(BaseModel):
    code: str
    name: str
    position: int
    deals: int


class CurrencyVolume(BaseModel):
    currency: str
    deals: int
    size_mm: float


class BookRow(BaseModel):
    """One deal, with what its book and allocation look like (zeros when it has no book)."""

    deal_id: str
    name: str
    issuer: str
    currency: str
    size_mm: int
    stage_name: str
    launch_date: str | None
    tasks_done: int
    tasks_total: int
    blockers_open: int
    orders: int
    investors: int
    demand_k: int
    cover: float | None
    allocated_k: int
    allocation_state: str | None  # PROPOSED | APPROVED | None


class Mix(BaseModel):
    label: str
    demand_k: int
    share_pct: float


class ActivityDay(BaseModel):
    day: str  # YYYY-MM-DD
    events: int


class Count(BaseModel):
    label: str
    count: int


class ReportOverview(BaseModel):
    generated_at: str
    kpis: Kpis
    stages: list[StageRow]
    volume: list[CurrencyVolume]
    books: list[BookRow]
    mix_by_type: list[Mix]
    mix_by_region: list[Mix]
    activity: list[ActivityDay] = Field(default_factory=list)
    top_actions: list[Count] = Field(default_factory=list)
