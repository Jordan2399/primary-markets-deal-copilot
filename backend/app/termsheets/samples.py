"""Sample term sheets generated from a deal's booked data, for demos and tests.

"good" matches the booking. "bad" carries four deliberate errors so the red mismatches show:
a coupon that is 0.125% too high, a maturity a year late, a size 50m too small, and an ISIN
whose check digit is wrong.
"""

import random
from datetime import timedelta

from app.common.isin import make_isin
from app.deals.models import DealDetail
from app.deals.templates import add_years
from app.termsheets.models import SampleOut

DEFAULT_COUPON = 3.375
LISTINGS = {
    "EUR": "Luxembourg Stock Exchange (Euro MTF)",
    "USD": "New York Stock Exchange (NYSE)",
    "GBP": "London Stock Exchange (International Securities Market)",
    "CHF": "SIX Swiss Exchange",
}


def _wrong_check_digit(isin: str) -> str:
    return isin[:-1] + str((int(isin[-1]) + 3) % 10)


def render_sample(deal: DealDetail, variant: str) -> SampleOut:
    tranche = deal.tranches[0] if deal.tranches else None
    launch = deal.launch_date
    issue = launch + timedelta(days=7) if launch else None
    tenor = tranche.tenor_years if tranche else 5
    maturity = (tranche.maturity if tranche and tranche.maturity else None) or (
        add_years(issue, tenor) if issue else None
    )
    coupon = tranche.coupon if tranche and tranche.coupon is not None else DEFAULT_COUPON
    isin = tranche.isin if tranche and tranche.isin else None
    if isin is None:
        rng = random.Random(f"termsheet-{deal.id}")
        isin = make_isin("XS", "9999" + "".join(str(rng.randrange(10)) for _ in range(5)))
    size = float(deal.size_mm)
    fmt = tranche.format if tranche else "Reg S"

    if variant == "bad":
        coupon += 0.125
        size -= 50
        isin = _wrong_check_digit(isin)
        if maturity:
            maturity = add_years(maturity, 1)

    lines = [
        f"FINAL TERMS - {deal.issuer_name}",
        f"{deal.currency} {size:g} million {tenor}-year fixed rate senior unsecured notes",
        "",
        f"Issuer: {deal.issuer_name}",
        f"ISIN: {isin}",
        f"Currency: {deal.currency}",
        f"Aggregate nominal amount: {deal.currency} {size * 1_000_000:,.0f}",
        f"Coupon: {coupon:.3f}% per annum, payable annually in arrear",
        f"Issue date: {issue.isoformat() if issue else 'to be confirmed'}",
        f"Maturity date: {maturity.isoformat() if maturity else 'to be confirmed'}",
        f"Format: {fmt}",
        f"Listing: {LISTINGS.get(deal.currency, 'Not listed')}",
        "Governing law: English law",
        "",
        "This is a synthetic document created for demonstration. It is not an offer of securities.",
    ]
    return SampleOut(
        filename=f"{deal.id}-{variant}-termsheet.txt", text="\n".join(lines), variant=variant
    )
