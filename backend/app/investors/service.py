"""Investor use cases: the directory, a profile, a deal's investor network and target list."""

from collections import defaultdict

from app.core.errors import NotFoundError
from app.deals.service import DealService
from app.investors.models import (
    DealNetwork,
    Facet,
    Investor,
    InvestorOrder,
    InvestorPage,
    InvestorProfile,
    InvestorSummary,
    NetworkGroup,
    NetworkNode,
    Target,
)
from app.investors.repository import InvestorRepository
from app.investors.scoring import score_investor
from app.orderbook.repository import OrderBookRepository

# The columns the directory can be sorted by, mapped to the key used for sorting.
SORT_KEYS = {
    "name": lambda s: s.name.lower(),
    "orders": lambda s: -s.orders,
    "ordered": lambda s: -s.ordered_k,
    "participation": lambda s: -s.past_participation,
}


def _summaries(
    investors: list[Investor], orders: list[InvestorOrder]
) -> dict[str, InvestorSummary]:
    """Attach the activity numbers (deals, orders, amounts) to every investor."""
    by_investor: dict[str, list[InvestorOrder]] = defaultdict(list)
    for order in orders:
        by_investor[order.investor_id].append(order)
    result: dict[str, InvestorSummary] = {}
    for inv in investors:
        mine = by_investor.get(inv.id, [])
        result[inv.id] = InvestorSummary(
            **inv.model_dump(),
            deals=len({o.deal_id for o in mine}),
            orders=len(mine),
            ordered_k=sum(o.amount_k for o in mine),
            allocated_k=sum(o.allocated_k or 0 for o in mine),
        )
    return result


def _facets(values: list[str]) -> list[Facet]:
    """Count each distinct value, largest group first (ties alphabetical, so output is stable)."""
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[value] += 1
    return [
        Facet(value=v, count=c) for v, c in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def _groups(nodes: list[NetworkNode], key: str, total_k: int) -> list[NetworkGroup]:
    """Roll the nodes up by `type` or `region` for the legend; largest demand first."""
    demand: dict[str, int] = defaultdict(int)
    count: dict[str, int] = defaultdict(int)
    for node in nodes:
        label = getattr(node, key)
        demand[label] += node.amount_k
        count[label] += 1
    return [
        NetworkGroup(
            label=label,
            investors=count[label],
            demand_k=amount,
            share_pct=round(100 * amount / total_k, 1) if total_k else 0.0,
        )
        for label, amount in sorted(demand.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


class InvestorService:
    def __init__(
        self, repo: InvestorRepository, book: OrderBookRepository, deals: DealService
    ) -> None:
        self._repo = repo
        self._book = book  # used for "who is in THIS deal's book"
        self._deals = deals

    async def directory(
        self,
        *,
        q: str | None,
        type_: str | None,
        region: str | None,
        real_money: bool | None,
        esg: bool | None,
        sort: str,
        page: int,
        page_size: int,
    ) -> InvestorPage:
        """Filter, sort and page the investors. Facet counts ignore the filters on purpose, so the
        filter chips keep showing every choice instead of disappearing once one is selected."""
        investors = await self._repo.list_investors()
        summaries = _summaries(investors, await self._repo.list_orders())
        everyone = list(summaries.values())

        needle = (q or "").strip().lower()
        matches = [
            s
            for s in everyone
            if (not needle or needle in s.name.lower() or needle == s.id.lower())
            and (type_ is None or s.type == type_)
            and (region is None or s.region == region)
            and (real_money is None or s.real_money == real_money)
            and (esg is None or s.esg_focus == esg)
        ]
        # Second key (id) makes the order stable when the main key ties.
        matches.sort(key=lambda s: (SORT_KEYS.get(sort, SORT_KEYS["name"])(s), s.id))
        start = (page - 1) * page_size
        return InvestorPage(
            total=len(matches),
            page=page,
            page_size=page_size,
            items=matches[start : start + page_size],
            types=_facets([s.type for s in everyone]),
            regions=_facets([s.region for s in everyone]),
        )

    async def profile(self, investor_id: str) -> InvestorProfile:
        investors = await self._repo.list_investors()
        orders = await self._repo.list_orders()
        summaries = _summaries(investors, orders)
        me = summaries.get(investor_id)
        if me is None:
            raise NotFoundError(f"Investor {investor_id} was not found.")
        # "Investors like this": same type and region, closest typical ticket first.
        peers = [
            s
            for s in summaries.values()
            if s.id != me.id and s.type == me.type and s.region == me.region
        ]
        peers.sort(key=lambda s: (abs(s.ticket_mean_k - me.ticket_mean_k), s.id))
        mine = [o for o in orders if o.investor_id == investor_id]
        return InvestorProfile(investor=me, orders=mine, similar=peers[:5])

    async def network(self, deal_id: str) -> DealNetwork:
        """The investors in one deal's book, one node each, with the legend roll-ups."""
        deal = await self._deals.get_deal(deal_id)  # 404 for an unknown deal
        rows = await self._book.list_orders(deal_id)
        nodes_by_id: dict[str, NetworkNode] = {}
        for row in rows:
            node = nodes_by_id.get(row.investor_id)
            if node is None:
                nodes_by_id[row.investor_id] = NetworkNode(
                    investor_id=row.investor_id,
                    name=row.investor_name,
                    type=row.investor_type,
                    region=row.region,
                    real_money=row.real_money,
                    amount_k=row.amount_k,
                    orders=1,
                )
            else:  # the same investor placed more than one order: sum them
                node.amount_k += row.amount_k
                node.orders += 1
        nodes = sorted(nodes_by_id.values(), key=lambda n: (-n.amount_k, n.investor_id))
        total = sum(n.amount_k for n in nodes)
        return DealNetwork(
            deal_id=deal.id,
            deal_name=deal.name,
            currency=deal.currency,
            deal_size_k=int(deal.size_mm * 1000),
            total_demand_k=total,
            nodes=nodes,
            by_type=_groups(nodes, "type", total),
            by_region=_groups(nodes, "region", total),
        )

    async def targets(self, deal_id: str, limit: int) -> list[Target]:
        """Investors NOT yet in the deal's book, best fit first."""
        deal = await self._deals.get_deal(deal_id)
        size_k = int(deal.size_mm * 1000)
        in_book = await self._book.list_orders(deal_id)
        booked_ids = {o.investor_id for o in in_book}

        # Region shares of the current book (None while it is empty: no region bonus then).
        total = sum(o.amount_k for o in in_book)
        region_demand: dict[str, int] = defaultdict(int)
        for o in in_book:
            region_demand[o.region] += o.amount_k

        investors = await self._repo.list_investors()
        summaries = _summaries(investors, await self._repo.list_orders())
        ranked: list[Target] = []
        for inv in investors:
            if inv.id in booked_ids:
                continue
            share = region_demand.get(inv.region, 0) / total if total else None
            score, reasons, cautions = score_investor(
                inv, deal_size_k=size_k, currency=deal.currency, region_share=share
            )
            ranked.append(
                Target(investor=summaries[inv.id], score=score, reasons=reasons, cautions=cautions)
            )
        # Best score first; the id breaks ties so the list is stable between calls.
        ranked.sort(key=lambda t: (-t.score, t.investor.id))
        return ranked[:limit]
