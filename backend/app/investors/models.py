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
