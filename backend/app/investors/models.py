"""Synthetic investors. Every name is invented."""

from pydantic import BaseModel

INVESTOR_TYPES = (
    "asset_manager",
    "insurer",
    "pension_fund",
    "bank_treasury",
    "official_institution",
    "hedge_fund",
)

REGIONS = (
    "UK",
    "DACH",
    "France",
    "Benelux",
    "Nordics",
    "Southern Europe",
    "US",
    "Asia",
    "Middle East",
)

# "Real money" accounts hold bonds for the long term. Banks and hedge funds trade more actively.
REAL_MONEY_TYPES = frozenset({"asset_manager", "insurer", "pension_fund", "official_institution"})


class Investor(BaseModel):
    id: str
    name: str
    type: str
    region: str
    real_money: bool
    esg_focus: bool
    ticket_mean_k: int  # typical order size in thousands of the deal currency
    ticket_std_k: int
    past_participation: int  # how many past deals the investor took part in


# ---------------------------------------------------------------------------------------------
# API shapes for the investor pages (Day 3b). The `Investor` above is the stored profile; the
# models below add what the screens need: activity numbers, a deal's network and target list.
# Amounts are whole thousands of the deal currency ("k"), as everywhere else in the project.
# ---------------------------------------------------------------------------------------------


class InvestorOrder(BaseModel):
    """One order of one investor on one deal, with the allocation it received (if any)."""

    investor_id: str
    order_id: str
    deal_id: str
    deal_name: str
    stage_name: str
    currency: str
    deal_size_mm: float
    amount_k: int
    limit_bp: int
    placed_at: str  # ISO timestamp
    allocated_k: int | None = None  # None until an allocation has been proposed for the deal


class InvestorSummary(Investor):
    """An investor plus a roll-up of everything they did in the books we hold."""

    deals: int = 0  # number of distinct deals with at least one order
    orders: int = 0
    ordered_k: int = 0
    allocated_k: int = 0


class Facet(BaseModel):
    """One filter choice with how many investors it matches (counted over all investors)."""

    value: str
    count: int


class InvestorPage(BaseModel):
    """One page of the directory, plus the facets that drive the filter chips."""

    total: int  # investors matching the filters, across all pages
    page: int
    page_size: int
    items: list[InvestorSummary]
    types: list[Facet]
    regions: list[Facet]


class InvestorProfile(BaseModel):
    """Everything on the investor detail page."""

    investor: InvestorSummary
    orders: list[InvestorOrder]
    similar: list[InvestorSummary]  # same type and region with the closest typical ticket


class NetworkNode(BaseModel):
    """An investor that has an order in the deal's book (orders of one investor are summed)."""

    investor_id: str
    name: str
    type: str
    region: str
    real_money: bool
    amount_k: int
    orders: int


class NetworkGroup(BaseModel):
    """Demand of one investor type or region, for the legend next to the graph."""

    label: str
    investors: int
    demand_k: int
    share_pct: float


class DealNetwork(BaseModel):
    deal_id: str
    deal_name: str
    currency: str
    deal_size_k: int
    total_demand_k: int
    nodes: list[NetworkNode]
    by_type: list[NetworkGroup]
    by_region: list[NetworkGroup]


class Target(BaseModel):
    """An investor worth calling for a deal, with the reasons behind the score."""

    investor: InvestorSummary
    score: int  # 0-100
    reasons: list[str]  # plain-language reasons, one per factor that added points
    cautions: list[str]  # factors that count against the investor (may be empty)
