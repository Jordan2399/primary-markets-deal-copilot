"""Deterministic generator for the 150 synthetic investors."""

import random

from app.investors.models import REAL_MONEY_TYPES, REGIONS, Investor

SEED_VALUE = "deal-copilot-2026"

_PREFIXES = (
    "Aldergate",
    "Brightwater",
    "Corvane",
    "Dunmore",
    "Eastvale",
    "Fairhaven",
    "Glenmoor",
    "Harrowgate",
    "Ironbridge",
    "Juniper",
    "Kingsmere",
    "Larchwood",
    "Marlowe",
    "Northcote",
    "Oakhurst",
    "Pennine",
    "Quillon",
    "Ravensworth",
    "Stonehaven",
    "Thornfield",
    "Upland",
    "Valmont",
    "Westerly",
    "Yarrow",
    "Zephyr",
    "Ashdown",
    "Beaumont",
    "Cresswell",
    "Delmar",
    "Elmstead",
    "Foxglove",
    "Grantley",
    "Hawthorne",
    "Ingleby",
    "Jessamy",
    "Kestrel Point",
    "Lowther",
    "Montrose",
    "Nethercott",
    "Orchard Lane",
    "Pemberton",
    "Rosedale",
    "Salcombe",
    "Tamarind",
    "Ullswater",
    "Verity",
    "Wexcombe",
    "Yewdale",
    "Ainsley",
    "Brackenridge",
)

# type -> (count, name suffixes, mean ticket in thousands)
_TYPES: dict[str, tuple[int, tuple[str, ...], int]] = {
    "asset_manager": (55, ("Capital", "Asset Management", "Investment Partners"), 20_000),
    "insurer": (25, ("Life", "Assurance", "Reinsurance"), 25_000),
    "pension_fund": (20, ("Pension Fund", "Retirement Scheme"), 40_000),
    "bank_treasury": (20, ("Bank Treasury", "Treasury Services"), 10_000),
    "official_institution": (
        10,
        ("Reserve Office", "Sovereign Fund", "Development Agency"),
        50_000,
    ),
    "hedge_fund": (20, ("Credit Opportunities", "Macro Fund"), 15_000),
}

# Regions are weighted towards Europe, as a euro-bond book would be.
_REGION_WEIGHTS = (14, 18, 14, 10, 8, 10, 12, 8, 6)


def build_investors() -> list[Investor]:
    rng = random.Random(f"{SEED_VALUE}-investors")
    prefixes = list(_PREFIXES)
    rng.shuffle(prefixes)
    investors: list[Investor] = []
    index = 0
    for type_name, (count, suffixes, mean) in _TYPES.items():
        for _ in range(count):
            prefix = prefixes[index % len(prefixes)]
            suffix = suffixes[rng.randrange(len(suffixes))]
            ticket_mean = int(round(mean * rng.uniform(0.5, 1.8) / 500) * 500)
            ticket_std = max(500, int(round(ticket_mean * 0.3 / 500) * 500))
            investors.append(
                Investor(
                    id=f"INV-{index + 1:03d}",
                    name=f"{prefix} {suffix}",
                    type=type_name,
                    region=rng.choices(REGIONS, weights=_REGION_WEIGHTS)[0],
                    real_money=type_name in REAL_MONEY_TYPES,
                    esg_focus=rng.random()
                    < (0.55 if type_name in {"pension_fund", "insurer"} else 0.3),
                    ticket_mean_k=ticket_mean,
                    ticket_std_k=ticket_std,
                    past_participation=rng.randint(0, 12),
                )
            )
            index += 1
    # Two investors can share a prefix and suffix: make the names unique and stable.
    seen: dict[str, int] = {}
    for inv in investors:
        count = seen.get(inv.name, 0)
        seen[inv.name] = count + 1
        if count:
            inv.name = f"{inv.name} {count + 1}"
    return investors
