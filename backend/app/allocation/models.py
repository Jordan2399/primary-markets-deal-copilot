"""Allocation models."""

from datetime import datetime

from pydantic import BaseModel, Field


class AllocationLine(BaseModel):
    order_id: str
    investor_id: str
    investor_name: str
    investor_type: str
    band: int | None  # 1 is the highest priority; None when the order was not eligible
    score: int | None
    ordered_k: int
    allocated_k: int
    fill_pct: float
    note: str


class BandSummary(BaseModel):
    band: int
    orders: int
    demand_k: int
    allocated_k: int
    scale_pct: float  # allocated divided by demand


class AllocationResult(BaseModel):
    deal_size_k: int
    final_spread_bp: int
    eligible_demand_k: int
    total_allocated_k: int
    status: str  # oversubscribed | undersubscribed
    bands: list[BandSummary]
    lines: list[AllocationLine]


class Proposal(AllocationResult):
    id: str
    deal_id: str
    state: str  # PROPOSED | APPROVED | SUPERSEDED
    proposed_by: str
    proposed_at: datetime
    approved_by: str | None = None
    approved_at: datetime | None = None
    explanation: str
    explanation_source: str  # a model name, or "template" when no model was available


class ProposalSummary(BaseModel):
    id: str
    deal_id: str
    state: str
    final_spread_bp: int
    total_allocated_k: int
    deal_size_k: int
    proposed_by: str
    proposed_at: datetime
    approved_by: str | None = None


class ProposeRequest(BaseModel):
    final_spread_bp: int | None = Field(None, ge=0, le=1000)
