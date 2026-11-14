"""Allocation rules: propose, explain, and approve with four eyes."""

import hashlib
import json
import re
import uuid
from datetime import UTC, datetime

from app.allocation.engine import EngineOrder, allocate
from app.allocation.models import AllocationResult, Proposal, ProposalSummary
from app.allocation.repository import AllocationRepository
from app.audit.models import build_event
from app.core.errors import ConflictError, ForbiddenError, NotFoundError
from app.core.security import CurrentUser
from app.llm.base import ChatMessage, LLMError, LLMProvider
from app.orderbook.anomalies import excluded_order_ids
from app.orderbook.metrics import build_ladder, suggest_final_spread
from app.orderbook.service import BOOK_BUILDING_POSITION, BookState, OrderBookService

EXPLAIN_SYSTEM = (
    "You explain a bond allocation to a syndicate manager in 4 to 6 plain sentences. "
    "Use only the numbers in the facts. Never invent figures. Do not give advice. "
    "Say how many orders were in each priority band and how much each band was scaled back."
)


def template_explanation(result: AllocationResult) -> str:
    """A plain explanation that needs no model. Used when the model is unavailable."""
    parts = [
        f"The book is {result.status} at a final spread of {result.final_spread_bp}bp: eligible demand "
        f"is {result.eligible_demand_k:,}k against a deal of {result.deal_size_k:,}k, and "
        f"{result.total_allocated_k:,}k is allocated."
    ]
    for band in result.bands:
        parts.append(
            f"Band {band.band}: {band.orders} orders asked for {band.demand_k:,}k and received "
            f"{band.allocated_k:,}k ({band.scale_pct}%)."
        )
    excluded = sum(1 for line in result.lines if line.band is None)
    if excluded:
        parts.append(
            f"{excluded} orders were not eligible (anomaly rules or a limit above the final spread)."
        )
    return " ".join(parts)


# Matches numbers like 750, 1,250,000 or 3.5 (digits with optional thousands commas and decimals).
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text: str) -> set[float]:
    """All numbers found in a text, as floats, so 1,250 and 1250.0 compare equal."""
    found: set[float] = set()
    for raw in _NUMBER.findall(text):
        try:
            found.add(float(raw.replace(",", "").rstrip(".")))
        except ValueError:
            continue
    return found


def acceptable_explanation(text: str, facts: dict[str, object]) -> bool:
    """Is the model's wording safe to show? It must read like prose and invent no large figure.

    Rejected: empty or tiny replies, JSON or code blocks, very long replies, and any amount
    (a number of 100 or more) that is not one of the engine's own numbers. A rejected reply is
    replaced by the template, so a weak model can make the text plainer but never wrong.
    """
    # Too short, too long, or starting like JSON/code: not prose.
    if not 40 <= len(text) <= 1500 or text[0] in "{[`":
        return False
    # Every number the engine computed is allowed; small numbers (< 100) are ignored, e.g. 'two'.
    allowed = _numbers(json.dumps(facts))
    return all(n in allowed for n in _numbers(text) if n >= 100)


def _facts(result: AllocationResult) -> dict[str, object]:
    return {
        "status": result.status,
        "deal_size_k": result.deal_size_k,
        "final_spread_bp": result.final_spread_bp,
        "eligible_demand_k": result.eligible_demand_k,
        "total_allocated_k": result.total_allocated_k,
        "bands": [b.model_dump() for b in result.bands],
        "orders_not_eligible": sum(1 for line in result.lines if line.band is None),
    }


class AllocationService:
    def __init__(
        self, repo: AllocationRepository, book: OrderBookService, llm: LLMProvider
    ) -> None:
        self._repo = repo
        self._book = book
        self._llm = llm

    def _engine_orders(self, state: BookState) -> list[EngineOrder]:
        reasons = {a.order_id: a.rule.replace("_", " ") for a in state.anomalies if a.excludes}
        assert state.params is not None
        return [
            EngineOrder(
                order_id=o.id,
                investor_id=o.investor_id,
                investor_name=o.investor_name,
                investor_type=o.investor_type,
                amount_k=o.amount_k,
                limit_bp=o.limit_bp,
                placed_minute=(o.placed_at - state.params.open_at).total_seconds() / 60,
                past_participation=o.past_participation,
                excluded_reason=reasons.get(o.id),
            )
            for o in state.orders
        ]

    async def preview(self, deal_id: str, final_spread_bp: int | None) -> AllocationResult:
        state = await self._book.state(deal_id)
        if state.deal.stage_position < BOOK_BUILDING_POSITION:
            raise ConflictError(
                f"Allocation starts at Book building. This deal is at {state.deal.stage_name}."
            )
        if not state.orders or state.params is None:
            raise ConflictError("The order book is empty. Simulate a book first.")
        spread = final_spread_bp
        if spread is None:
            valid = [o for o in state.orders if o.id not in excluded_order_ids(state.anomalies)]
            spread = suggest_final_spread(
                build_ladder(valid, state.deal_size_k, state.params.ipt_bp)
            )
        assert spread is not None
        return allocate(self._engine_orders(state), state.deal_size_k, spread)

    async def _explain(self, result: AllocationResult) -> tuple[str, str, str | None]:
        """Return (text, source, prompt hash). The model only words the result; it never changes it."""
        messages: list[ChatMessage] = [
            {"role": "system", "content": EXPLAIN_SYSTEM},
            {"role": "user", "content": f"<facts>{json.dumps(_facts(result))}</facts>"},
        ]
        digest = hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]
        try:
            text = (await self._llm.chat(messages, temperature=0.2)).strip()
        except LLMError:
            return template_explanation(result), "template", digest
        # Fall back to the template when the wording is empty, odd-looking or invents figures.
        if not acceptable_explanation(text, _facts(result)):
            return template_explanation(result), "template", digest
        return text, self._llm.model, digest

    async def propose(
        self, deal_id: str, final_spread_bp: int | None, user: CurrentUser
    ) -> Proposal:
        result = await self.preview(deal_id, final_spread_bp)
        text, source, digest = await self._explain(result)
        proposal = Proposal(
            **result.model_dump(),
            id=f"ALLOC-{uuid.uuid4().hex[:8].upper()}",
            deal_id=deal_id,
            state="PROPOSED",
            proposed_by=user.name,
            proposed_at=datetime.now(UTC),
            explanation=text,
            explanation_source=source,
        )
        event = build_event(
            user,
            "allocation.propose",
            "allocation",
            proposal.id,
            deal_id=deal_id,
            details={
                "final_spread_bp": proposal.final_spread_bp,
                "total_allocated_k": proposal.total_allocated_k,
                "status": proposal.status,
            },
            model=source if source != "template" else None,
            prompt_hash=digest if source != "template" else None,
        )
        await self._repo.save_proposal(proposal, event)
        return proposal

    async def get(self, proposal_id: str) -> Proposal:
        proposal = await self._repo.get(proposal_id)
        if proposal is None:
            raise NotFoundError(f"Allocation proposal {proposal_id} was not found.")
        return proposal

    async def list(self, deal_id: str) -> list[ProposalSummary]:
        await self._book.state(deal_id)  # 404 for an unknown deal
        return await self._repo.list(deal_id)

    async def approve(self, proposal_id: str, user: CurrentUser) -> Proposal:
        proposal = await self.get(proposal_id)
        if proposal.state != "PROPOSED":
            raise ConflictError(
                f"This proposal is {proposal.state.lower()} and cannot be approved.",
                details={"state": proposal.state},
            )
        if proposal.proposed_by == user.name:
            raise ForbiddenError(
                "Four-eyes rule: the person who proposed an allocation cannot approve it.",
                details={"proposed_by": proposal.proposed_by},
            )
        event = build_event(
            user,
            "allocation.approve",
            "allocation",
            proposal.id,
            deal_id=proposal.deal_id,
            details={
                "proposed_by": proposal.proposed_by,
                "total_allocated_k": proposal.total_allocated_k,
            },
        )
        done = await self._repo.approve(proposal_id, user.name, datetime.now(UTC), event)
        if not done:  # someone else approved or a newer proposal replaced it a moment ago
            raise ConflictError("This proposal was changed by someone else. Reload and try again.")
        return await self.get(proposal_id)
