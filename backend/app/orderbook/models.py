"""Order book models: orders, book parameters, anomalies and metrics."""

from datetime import datetime

from pydantic import BaseModel, Field

# Amounts are whole thousands of the deal currency ("k"). 750m is 750_000.
INCREMENT_K = 100  # minimum denomination and rounding step: 100,000


class BookParams(BaseModel):
    open_at: datetime
    close_at: datetime
    ipt_bp: int  # initial price thoughts, as a spread over mid-swaps in basis points


class OrderRow(BaseModel):
    """An order joined with facts about its investor."""

    id: str
    investor_id: str
    investor_name: str
    investor_type: str
    region: str
    real_money: bool
    ticket_mean_k: int
    ticket_std_k: int
    past_participation: int
    amount_k: int
    limit_bp: int  # the investor stays in as long as the final spread is at or above this
    placed_at: datetime


class NewOrder(BaseModel):
    id: str
    investor_id: str
    amount_k: int
    limit_bp: int
    placed_at: datetime


class Anomaly(BaseModel):
    order_id: str
    rule: str  # duplicate | ticket_zscore | after_close | exceeds_deal_size
    severity: str  # high | medium
    excludes: bool  # excluded from allocation
    message: str


class OrderOut(BaseModel):
    id: str
    investor_id: str
    investor_name: str
    investor_type: str
    region: str
    amount_k: int
    limit_bp: int
    placed_at: datetime
    flags: list[str] = Field(default_factory=list)


class Bucket(BaseModel):
    label: str
    demand_k: int
    orders: int
    share_pct: float


class LadderLevel(BaseModel):
    spread_bp: int
    demand_k: int
    cover: float


class TimelinePoint(BaseModel):
    minute: int
    cumulative_demand_k: int
    orders: int


class BookMetrics(BaseModel):
    deal_size_k: int
    order_count: int
    valid_order_count: int
    investor_count: int
    total_demand_k: int  # every order, including flagged ones
    valid_demand_k: int  # orders that would take part in an allocation
    cover_ratio: float  # valid demand divided by deal size
    real_money_share_pct: float
    anomaly_count: int
    by_type: list[Bucket]
    by_region: list[Bucket]
    ladder: list[LadderLevel]
    timeline: list[TimelinePoint]
    suggested_final_spread_bp: int | None


class OrderBook(BaseModel):
    deal_id: str
    params: BookParams | None
    metrics: BookMetrics | None
    orders: list[OrderOut]
    anomalies: list[Anomaly]


class SimulateRequest(BaseModel):
    seed: int = Field(1, ge=0, le=9999)
    target_cover: float = Field(2.8, ge=1.0, le=6.0)
    anomalies: int = Field(4, ge=0, le=10)
    extend: bool = False
