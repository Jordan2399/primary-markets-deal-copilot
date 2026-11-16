"""Reports: roll-ups across all deals. Read-only; nothing here changes data."""

import csv
import io
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from app.allocation.service import AllocationService
from app.audit.service import AuditService
from app.deals.models import DealSummary
from app.deals.service import DealService
from app.deals.templates import STAGE_BY_CODE
from app.investors.models import Investor, InvestorOrder
from app.investors.repository import InvestorRepository
from app.reports.models import (
    ActivityDay,
    BookRow,
    Count,
    CurrencyVolume,
    Kpis,
    Mix,
    ReportOverview,
    StageRow,
)

BOOK_BUILDING = STAGE_BY_CODE["book_building"].position
ACTIVITY_DAYS = 14
# Spreadsheet programs run text that starts with one of these as a formula. Cells from users
# (deal names) get a leading apostrophe so an export can never carry a formula into Excel.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value: object) -> object:
    text = str(value)
    return "'" + text if text.startswith(_FORMULA_START) else value


def _mix(demand: dict[str, int]) -> list[Mix]:
    """Largest first; shares add up to 100 (rounded to one decimal)."""
    total = sum(demand.values())
    rows = sorted(demand.items(), key=lambda kv: (-kv[1], kv[0]))
    return [
        Mix(label=k, demand_k=v, share_pct=round(100 * v / total, 1) if total else 0.0)
        for k, v in rows
    ]


class ReportService:
    def __init__(
        self,
        deals: DealService,
        investors: InvestorRepository,
        allocation: AllocationService,
        audit: AuditService,
        *,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._deals = deals
        self._investors = investors
        self._allocation = allocation
        self._audit = audit
        self._now = now

    async def _rows(
        self,
    ) -> tuple[list[DealSummary], list[BookRow], list[InvestorOrder], dict[str, Investor]]:
        """One row per deal with its book and allocation numbers."""
        deals = await self._deals.list_deals()
        orders = await self._investors.list_orders()
        investors = {i.id: i for i in await self._investors.list_investors()}
        by_deal: dict[str, list[InvestorOrder]] = defaultdict(list)
        for order in orders:
            by_deal[order.deal_id].append(order)

        rows: list[BookRow] = []
        for deal in deals:
            book = by_deal.get(deal.id, [])
            demand = sum(o.amount_k for o in book)
            # One proposal counts per deal: an approved one wins over a pending one.
            proposals = await self._allocation.list(deal.id)
            state = None
            for wanted in ("APPROVED", "PROPOSED"):
                if any(p.state == wanted for p in proposals):
                    state = wanted
                    break
            rows.append(
                BookRow(
                    deal_id=deal.id,
                    name=deal.name,
                    issuer=deal.issuer_name,
                    currency=deal.currency,
                    size_mm=deal.size_mm,
                    stage_name=deal.stage_name,
                    launch_date=deal.launch_date.isoformat() if deal.launch_date else None,
                    tasks_done=deal.tasks_done,
                    tasks_total=deal.tasks_total,
                    blockers_open=deal.blockers_open,
                    orders=len(book),
                    investors=len({o.investor_id for o in book}),
                    demand_k=demand,
                    cover=round(demand / (deal.size_mm * 1000), 2)
                    if book and deal.size_mm
                    else None,
                    allocated_k=sum(o.allocated_k or 0 for o in book),
                    allocation_state=state,
                )
            )
        return deals, rows, orders, investors

    async def overview(self) -> ReportOverview:
        deals, rows, orders, investors = await self._rows()
        stages = await self._deals.list_stages()

        active = [d for d in deals if not d.is_complete]
        covers = [r.cover for r in rows if r.cover is not None]
        kpis = Kpis(
            active_deals=len(active),
            in_market=sum(1 for d in active if d.stage_position >= BOOK_BUILDING),
            completed_deals=len(deals) - len(active),
            orders=len(orders),
            investors_active=len({o.investor_id for o in orders}),
            avg_cover=round(sum(covers) / len(covers), 2) if covers else None,
            pending_approvals=sum(1 for r in rows if r.allocation_state == "PROPOSED"),
            blocking_tasks=sum(d.blockers_open for d in active),
        )

        per_stage = Counter(d.stage_code for d in deals)
        stage_rows = [
            StageRow(code=s.code, name=s.name, position=s.position, deals=per_stage.get(s.code, 0))
            for s in sorted(stages, key=lambda s: s.position)
        ]

        volume: dict[str, list[float]] = defaultdict(lambda: [0, 0.0])
        for d in deals:
            volume[d.currency][0] += 1
            volume[d.currency][1] += d.size_mm
        volumes = [
            CurrencyVolume(currency=c, deals=int(v[0]), size_mm=v[1])
            for c, v in sorted(volume.items())
        ]

        by_type: dict[str, int] = defaultdict(int)
        by_region: dict[str, int] = defaultdict(int)
        for o in orders:
            inv = investors.get(o.investor_id)
            if inv:
                by_type[inv.type] += o.amount_k
                by_region[inv.region] += o.amount_k

        activity, top = await self._activity()
        return ReportOverview(
            generated_at=self._now().isoformat(),
            kpis=kpis,
            stages=stage_rows,
            volume=volumes,
            books=rows,
            mix_by_type=_mix(by_type),
            mix_by_region=_mix(by_region),
            activity=activity,
            top_actions=top,
        )

    async def _activity(self) -> tuple[list[ActivityDay], list[Count]]:
        """Audit events per day for the last two weeks (days without events count as 0)."""
        events = await self._audit.list_events(limit=500)
        today: date = self._now().date()
        days = [today - timedelta(days=n) for n in range(ACTIVITY_DAYS - 1, -1, -1)]
        per_day = Counter(e.ts[:10] for e in events)
        activity = [
            ActivityDay(day=d.isoformat(), events=per_day.get(d.isoformat(), 0)) for d in days
        ]
        top = [Count(label=a, count=n) for a, n in Counter(e.action for e in events).most_common(6)]
        return activity, top

    async def pipeline_csv(self) -> str:
        """The deal table as CSV, for Excel. UTF-8 with a BOM so Excel shows accents correctly."""
        _, rows, _, _ = await self._rows()
        out = io.StringIO()
        out.write("﻿")
        writer = csv.writer(out)
        writer.writerow(
            [
                "Deal ID",
                "Deal",
                "Issuer",
                "Currency",
                "Size (m)",
                "Stage",
                "Launch date",
                "Tasks done",
                "Tasks total",
                "Blocking open",
                "Orders",
                "Investors",
                "Demand (k)",
                "Cover (x)",
                "Allocated (k)",
                "Allocation",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    _safe_cell(v)
                    for v in (
                        r.deal_id,
                        r.name,
                        r.issuer,
                        r.currency,
                        r.size_mm,
                        r.stage_name,
                        r.launch_date or "",
                        r.tasks_done,
                        r.tasks_total,
                        r.blockers_open,
                        r.orders,
                        r.investors,
                        r.demand_k,
                        "" if r.cover is None else r.cover,
                        r.allocated_k,
                        r.allocation_state or "",
                    )
                ]
            )
        return out.getvalue()
