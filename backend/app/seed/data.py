"""Synthetic reference data. Every name here is invented; any resemblance to a real company is
accidental. Real client, investor or market data must never be added to this project."""

import random
from dataclasses import dataclass
from datetime import date, timedelta

from app.common.isin import make_isin
from app.deals.templates import STAGE_BY_CODE

SEED_VALUE = "deal-copilot-2026"


@dataclass(frozen=True)
class IssuerSeed:
    id: str
    name: str
    short: str
    sector: str
    country: str
    rating_band: str


ISSUERS: tuple[IssuerSeed, ...] = (
    IssuerSeed("ISS-001", "Nordvik Energie AG", "Nordvik", "Utilities", "DE", "A-"),
    IssuerSeed("ISS-002", "Calder & Hayes Telecom plc", "Calder & Hayes", "Telecom", "GB", "BBB+"),
    IssuerSeed("ISS-003", "Meridian Rail Holding SA", "Meridian Rail", "Industrials", "FR", "A"),
    IssuerSeed("ISS-004", "Aurelia Water NV", "Aurelia Water", "Utilities", "NL", "A+"),
    IssuerSeed("ISS-005", "Solenta Renovables SA", "Solenta", "Utilities", "ES", "BBB"),
    IssuerSeed("ISS-006", "Brenner Logistik GmbH", "Brenner", "Industrials", "DE", "BBB"),
    IssuerSeed("ISS-007", "Lysander Pharma AB", "Lysander", "Healthcare", "SE", "A"),
    IssuerSeed("ISS-008", "Cobalt Ridge Mining plc", "Cobalt Ridge", "Materials", "GB", "BBB-"),
    IssuerSeed("ISS-009", "Alpenhof Insurance AG", "Alpenhof", "Financials", "CH", "AA-"),
    IssuerSeed("ISS-010", "Veridian Motors SpA", "Veridian", "Autos", "IT", "BBB-"),
    IssuerSeed("ISS-011", "Harbourline Ports plc", "Harbourline", "Transport", "IE", "BBB+"),
    IssuerSeed("ISS-012", "Kestrel Real Estate SA", "Kestrel", "Real estate", "BE", "BBB"),
    IssuerSeed("ISS-013", "Montclair Retail SAS", "Montclair", "Consumer", "FR", "BBB"),
    IssuerSeed("ISS-014", "Tavira Banco SA", "Tavira", "Financials", "PT", "BBB+"),
    IssuerSeed("ISS-015", "Oberon Semiconductors NV", "Oberon", "Technology", "NL", "A-"),
    IssuerSeed("ISS-016", "Fennimore Foods plc", "Fennimore", "Consumer", "GB", "BBB+"),
    IssuerSeed("ISS-017", "Linden Utilities Oy", "Linden", "Utilities", "FI", "A"),
    IssuerSeed("ISS-018", "Ostrava Steelworks AS", "Ostrava", "Materials", "CZ", "BB+"),
    IssuerSeed("ISS-019", "Praia Telecom SA", "Praia", "Telecom", "PT", "BBB"),
    IssuerSeed("ISS-020", "Sable Aerospace Group SA", "Sable", "Industrials", "FR", "A-"),
    IssuerSeed("ISS-021", "Danube Bank AG", "Danube Bank", "Financials", "AT", "A"),
    IssuerSeed("ISS-022", "Redwood Capital Holdings Inc", "Redwood", "Financials", "US", "A-"),
    IssuerSeed("ISS-023", "Ashgrove Healthcare Inc", "Ashgrove", "Healthcare", "US", "BBB+"),
    IssuerSeed("ISS-024", "Nimbus Cloud Systems Inc", "Nimbus", "Technology", "US", "A+"),
    IssuerSeed("ISS-025", "Eder Hydro SA", "Eder Hydro", "Utilities", "CH", "AA-"),
)

ISSUER_BY_ID = {i.id: i for i in ISSUERS}


@dataclass(frozen=True)
class DealSeed:
    deal_id: str
    issuer_id: str
    currency: str
    size_mm: int
    tenor_years: int
    format: str
    stage_code: str
    done_in_stage: int  # tasks already DONE inside the current stage
    launch_offset_days: int  # launch date relative to the day the seed runs


DEALS: tuple[DealSeed, ...] = (
    # The demo deal: documentation is under way, so "what is left before launch?" is interesting.
    DealSeed("D-DEMO-001", "ISS-001", "EUR", 750, 5, "Reg S", "documentation", 2, 14),
    DealSeed("D-2026-001", "ISS-004", "EUR", 500, 10, "Domestic", "mandate", 3, 35),
    DealSeed("D-2026-002", "ISS-022", "USD", 1000, 5, "144A", "mandate", 1, 45),
    DealSeed("D-2026-003", "ISS-007", "EUR", 600, 7, "Reg S", "documentation", 4, 10),
    DealSeed("D-2026-004", "ISS-003", "EUR", 1000, 12, "Domestic", "pre_marketing", 3, 5),
    DealSeed("D-2026-005", "ISS-005", "EUR", 500, 6, "Reg S", "pre_marketing", 5, 3),
    DealSeed("D-2026-006", "ISS-024", "USD", 1500, 10, "144A", "launch", 2, 0),
    DealSeed("D-2026-007", "ISS-021", "EUR", 750, 5, "Domestic", "book_building", 2, 0),
    DealSeed("D-2026-008", "ISS-002", "GBP", 400, 8, "Reg S", "pricing", 1, 0),
    DealSeed("D-2026-009", "ISS-009", "CHF", 300, 7, "Domestic", "allocation", 2, -1),
    DealSeed("D-2026-010", "ISS-017", "EUR", 650, 9, "Reg S", "booking", 2, -3),
    DealSeed("D-2026-011", "ISS-014", "EUR", 500, 4, "Domestic", "booking", 5, -9),
)


def deal_name(spec: DealSeed) -> str:
    issuer = ISSUER_BY_ID[spec.issuer_id]
    return f"{issuer.short} {spec.currency} {spec.size_mm}m {spec.tenor_years}Y"


def launch_date(spec: DealSeed, today: date) -> date:
    return today + timedelta(days=spec.launch_offset_days)


def pricing_terms(spec: DealSeed) -> tuple[float | None, str | None]:
    """Coupon and ISIN exist once a deal has reached pricing. Deterministic per deal.

    The ISIN uses the 'XS' prefix and an NSIN starting with '9999' so that it is easy to see
    that it is invented. The check digit is valid.
    """
    if STAGE_BY_CODE[spec.stage_code].position < STAGE_BY_CODE["pricing"].position:
        return None, None
    rng = random.Random(f"{SEED_VALUE}-{spec.deal_id}")
    coupon = round(rng.uniform(2.5, 4.75), 3)
    nsin = "9999" + "".join(str(rng.randrange(10)) for _ in range(5))
    return coupon, make_isin("XS", nsin)
