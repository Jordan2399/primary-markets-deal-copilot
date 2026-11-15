"""Rule-based "who should we call" score for a deal. Pure functions, no database, no model.

The score is deliberately simple and explainable: a salesperson must be able to read WHY an
investor is on the list. Four factors add up to at most 100 points:

    real-money account ........ 30   holds bonds to maturity, so it stays in the book
    past participation ........ 25   has taken part in many earlier deals
    ticket fit ................ 30   typical order is a sensible share of this deal's size
    region gap ................ 15   adds a region the book does not have much of yet

The weights are constants so they can be tuned (and tested) in one place.
"""

from app.investors.models import Investor

POINTS_REAL_MONEY = 30
POINTS_PARTICIPATION = 25
POINTS_TICKET_FIT = 30
POINTS_REGION_GAP = 15

# Past participation counts up to this many deals; more adds nothing.
PARTICIPATION_CAP = 20

# A typical order between 1% and 10% of the deal is a good fit: big enough to matter, small enough
# that one investor does not dominate the book.
FIT_LOW = 0.01
FIT_HIGH = 0.10

# A region with less than this share of the book's demand counts as under-represented.
REGION_GAP_SHARE = 0.05


def ticket_fit(ticket_mean_k: int, deal_size_k: int) -> float:
    """How well the investor's typical order fits the deal, from 0.0 (poor) to 1.0 (ideal).

    Inside the 1-10% band the fit is 1. Below it the fit falls in proportion to how small the
    ticket is; above it, in proportion to how large. A zero-size deal has no fit.
    """
    if deal_size_k <= 0 or ticket_mean_k <= 0:
        return 0.0
    ratio = ticket_mean_k / deal_size_k
    if ratio < FIT_LOW:
        return ratio / FIT_LOW
    if ratio > FIT_HIGH:
        return FIT_HIGH / ratio
    return 1.0


def fmt_k(amount_k: int, currency: str) -> str:
    """12500 -> "EUR 12.5m", 800 -> "EUR 800k" (amounts are in thousands)."""
    if amount_k >= 1000:
        return f"{currency} {amount_k / 1000:g}m"
    return f"{currency} {amount_k}k"


def score_investor(
    investor: Investor,
    *,
    deal_size_k: int,
    currency: str,
    region_share: float | None,
) -> tuple[int, list[str], list[str]]:
    """Return (score, reasons, cautions) for one investor.

    `region_share` is the investor's region's share of the book's demand (0.0 to 1.0), or None when
    the book is still empty, in which case no region bonus is given (every region would qualify).
    """
    score = 0.0
    reasons: list[str] = []
    cautions: list[str] = []

    # 1. Real money: long-term holders are the backbone of a new-issue book.
    if investor.real_money:
        score += POINTS_REAL_MONEY
        reasons.append("Real-money account (holds to maturity)")
    else:
        cautions.append("Trading account: may sell soon after issue")

    # 2. Track record: points grow with the number of earlier deals, capped.
    taken = min(investor.past_participation, PARTICIPATION_CAP)
    if taken:
        score += POINTS_PARTICIPATION * taken / PARTICIPATION_CAP
        reasons.append(f"Took part in {investor.past_participation} past deals")
    else:
        cautions.append("No participation history")

    # 3. Ticket fit against this deal's size.
    fit = ticket_fit(investor.ticket_mean_k, deal_size_k)
    score += POINTS_TICKET_FIT * fit
    typical = fmt_k(investor.ticket_mean_k, currency)
    if fit >= 0.999:
        reasons.append(f"Typical ticket {typical} fits this deal")
    elif investor.ticket_mean_k < FIT_LOW * deal_size_k:
        cautions.append(f"Typical ticket {typical} is small for this deal")
    else:
        cautions.append(f"Typical ticket {typical} is large for this deal")

    # 4. Region gap: only meaningful once the book has orders.
    if region_share is not None and region_share < REGION_GAP_SHARE:
        score += POINTS_REGION_GAP
        reasons.append(f"{investor.region} is under-represented in the book")

    return round(score), reasons, cautions
