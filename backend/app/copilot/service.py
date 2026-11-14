"""Copilot service: run the graph, stream the answer, audit the call.

Two steps so that errors can still become proper HTTP errors:
  prepare()  runs the graph (database and embedding calls). Failures here return 4xx/5xx.
  stream()   streams the model's answer as server-sent events. Failures here are sent as an
             `error` event, because the HTTP status was already sent.

Events (event name -> JSON data):
  meta   {"intent", "sources": [...], "model", "conversation_id", "understood_as"}
         first, so the UI can show evidence early; `understood_as` is set when a follow-up was
         rewritten to stand alone
  token  {"text": "..."}                            many times
  done   {"cited": [...], "audit_id", "conversation_id"}  last, on success (the turn is saved)
  error  {"code", "message", "retry"}               instead of done; nothing is saved
"""

import hashlib
import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import structlog

from app.audit.models import build_event
from app.audit.service import AuditService
from app.conversations.service import ConversationService
from app.copilot.graph import build_copilot_graph
from app.copilot.models import ChatRequest, Source
from app.core.errors import AppError
from app.core.security import CurrentUser
from app.deals.service import DealService
from app.documents.service import DocumentService
from app.llm.base import ChatMessage, LLMProvider

log = structlog.get_logger()

_CITATION = re.compile(r"\[S(\d+)\]")


def sse(event: str, data: dict[str, Any]) -> str:
    """Format one Server-Sent Event: an event name line, a JSON data line, a blank line."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def prompt_hash(messages: list[ChatMessage]) -> str:
    """Short fingerprint of the exact prompt, stored in the audit trail (not the prompt itself)."""
    return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]


def cited_sources(answer: str, sources: list[Source]) -> list[str]:
    """Which source labels (S1, S2...) the answer really cites; unknown labels are dropped."""
    known = {s.id for s in sources}
    found: list[str] = []
    for number in _CITATION.findall(answer):
        label = f"S{number}"
        if label in known and label not in found:
            found.append(label)
    return found


@dataclass
class PreparedChat:
    """Everything the streaming step needs, produced by `prepare` before the first byte is sent."""

    request: ChatRequest
    user: CurrentUser
    intent: str
    sources: list[Source]
    messages: list[ChatMessage] | None
    direct_answer: str | None
    conversation_id: str | None = None  # the saved thread this turn belongs to
    understood_as: str | None = (
        None  # the rewritten question, only when it differs from the typed one
    )


class CopilotService:
    """Runs the graph, streams the answer, writes the audit entry and saves the turn."""

    def __init__(
        self,
        deals: DealService,
        docs: DocumentService,
        llm: LLMProvider,
        audit: AuditService,
        threads: ConversationService | None = None,  # None = no saved threads (older tests)
    ) -> None:
        self._llm = llm
        self._audit = audit
        self._threads = threads
        # The graph is compiled once per service instance.
        self._graph = build_copilot_graph(deals, docs, llm)

    async def prepare(self, request: ChatRequest, user: CurrentUser) -> PreparedChat:
        """Load the thread history, run the graph and return what is needed to stream the answer.

        Errors raised here (for example a foreign conversation id) become normal HTTP errors,
        because nothing has been streamed yet.
        """
        conversation_id: str | None = None
        if self._threads is not None:
            # History comes from the saved thread, never from the client, so it cannot be forged.
            conversation_id, history, _is_new = await self._threads.context_for(
                user, request.conversation_id
            )
            request = request.model_copy(
                update={"history": history, "conversation_id": conversation_id}
            )
        # Run rewrite -> classify -> lookup/retrieve -> compose and collect the final state.
        state = await self._graph.ainvoke({"request": request})
        question = state.get("question", request.message)
        return PreparedChat(
            request=request,
            user=user,
            intent=state.get("intent", "out_of_scope"),
            sources=state.get("sources", []),
            messages=state.get("messages"),
            direct_answer=state.get("direct_answer"),
            conversation_id=conversation_id,
            understood_as=question if question != request.message else None,
        )

    async def stream(self, prepared: PreparedChat) -> AsyncIterator[str]:
        """Yield the answer as SSE events: meta first, then tokens, then done or error."""
        sources = prepared.sources
        yield sse(
            "meta",
            {
                "intent": prepared.intent,
                "model": self._llm.model,
                "sources": [s.model_dump() for s in sources],
                "conversation_id": prepared.conversation_id,
                "understood_as": prepared.understood_as,
            },
        )

        # The answer is collected as it streams so it can be audited and saved afterwards.
        answer_parts: list[str] = []
        status = "ok"
        error: dict[str, Any] | None = None
        try:
            # A fixed answer (out of scope, pick a deal...) is sent as one chunk with no model call.
            if prepared.direct_answer is not None or prepared.messages is None:
                text = prepared.direct_answer or ""
                answer_parts.append(text)
                yield sse("token", {"text": text})
            else:
                async for piece in self._llm.stream(prepared.messages):
                    answer_parts.append(piece)
                    yield sse("token", {"text": piece})
        except AppError as exc:
            status = "error"
            error = {"code": exc.code, "message": exc.message, "retry": exc.retry}
        except Exception as exc:  # noqa: BLE001 - never leave the stream hanging
            log.error("copilot_stream_failed", error=type(exc).__name__, detail=str(exc)[:200])
            status = "error"
            error = {
                "code": "internal_error",
                "message": "The answer could not be completed.",
                "retry": True,
            }

        # Audit first (success or failure), then save the turn only if the answer succeeded.
        answer = "".join(answer_parts)
        audit_id = await self._record(prepared, answer, status)
        if error is not None:
            yield sse("error", error)
        else:
            cited = cited_sources(answer, sources)
            await self._save_turn(prepared, answer, cited, audit_id)
            yield sse(
                "done",
                {"cited": cited, "audit_id": audit_id, "conversation_id": prepared.conversation_id},
            )

    async def _save_turn(
        self, prepared: PreparedChat, answer: str, cited: list[str], audit_id: str | None
    ) -> None:
        """Save the question and answer in the thread. A failure is logged, never shown as an error."""
        if self._threads is None or prepared.conversation_id is None:
            return
        try:
            await self._threads.save_turn(
                prepared.user,
                prepared.conversation_id,
                prepared.request.deal_id,
                prepared.request.message,
                answer,
                sources=prepared.sources,
                cited=cited,
                intent=prepared.intent,
                audit_id=audit_id,
            )
        except Exception as exc:  # noqa: BLE001 - the user already has the answer; do not fail now
            log.error("conversation_save_failed", error=type(exc).__name__, detail=str(exc)[:200])

    async def _record(self, prepared: PreparedChat, answer: str, status: str) -> str | None:
        """Write the audit event. A failure to audit is logged but never breaks the answer."""
        request = prepared.request
        # llm_used is false for fixed answers, so the audit trail shows when no model ran.
        used_llm = prepared.messages is not None and prepared.direct_answer is None
        event = build_event(
            prepared.user,
            "copilot.chat",
            "copilot",
            request.deal_id or "global",
            deal_id=request.deal_id,
            details={
                "question": request.message[:500],
                "answer": answer[:2000],
                "intent": prepared.intent,
                "status": status,
                "llm_used": used_llm,
                "provider": self._llm.name,
            },
            model=self._llm.model if used_llm else None,
            prompt_hash=prompt_hash(prepared.messages) if prepared.messages else None,
            sources=[s.ref for s in prepared.sources],
        )
        try:
            await self._audit.record(event)
        except Exception as exc:  # noqa: BLE001
            log.error("audit_write_failed", error=type(exc).__name__, detail=str(exc)[:200])
            return None
        return event.id
