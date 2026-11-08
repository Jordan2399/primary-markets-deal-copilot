"""Copilot service: run the graph, stream the answer, audit the call.

Two steps so that errors can still become proper HTTP errors:
  prepare()  runs the graph (database and embedding calls). Failures here return 4xx/5xx.
  stream()   streams the model's answer as server-sent events. Failures here are sent as an
             `error` event, because the HTTP status was already sent.

Events (event name -> JSON data):
  meta   {"intent", "sources": [...], "model"}      first, so the UI can show evidence early
  token  {"text": "..."}                            many times
  done   {"cited": ["S1", ...], "audit_id": "..."}  last, on success
  error  {"code", "message", "retry"}               instead of done, on failure
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
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def prompt_hash(messages: list[ChatMessage]) -> str:
    return hashlib.sha256(json.dumps(messages, sort_keys=True).encode()).hexdigest()[:16]


def cited_sources(answer: str, sources: list[Source]) -> list[str]:
    known = {s.id for s in sources}
    found: list[str] = []
    for number in _CITATION.findall(answer):
        label = f"S{number}"
        if label in known and label not in found:
            found.append(label)
    return found


@dataclass
class PreparedChat:
    request: ChatRequest
    user: CurrentUser
    intent: str
    sources: list[Source]
    messages: list[ChatMessage] | None
    direct_answer: str | None


class CopilotService:
    def __init__(
        self,
        deals: DealService,
        docs: DocumentService,
        llm: LLMProvider,
        audit: AuditService,
    ) -> None:
        self._llm = llm
        self._audit = audit
        self._graph = build_copilot_graph(deals, docs, llm)

    async def prepare(self, request: ChatRequest, user: CurrentUser) -> PreparedChat:
        state = await self._graph.ainvoke({"request": request})
        return PreparedChat(
            request=request,
            user=user,
            intent=state.get("intent", "out_of_scope"),
            sources=state.get("sources", []),
            messages=state.get("messages"),
            direct_answer=state.get("direct_answer"),
        )

    async def stream(self, prepared: PreparedChat) -> AsyncIterator[str]:
        sources = prepared.sources
        yield sse(
            "meta",
            {
                "intent": prepared.intent,
                "model": self._llm.model,
                "sources": [s.model_dump() for s in sources],
            },
        )

        answer_parts: list[str] = []
        status = "ok"
        error: dict[str, Any] | None = None
        try:
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

        answer = "".join(answer_parts)
        audit_id = await self._record(prepared, answer, status)
        if error is not None:
            yield sse("error", error)
        else:
            yield sse("done", {"cited": cited_sources(answer, sources), "audit_id": audit_id})

    async def _record(self, prepared: PreparedChat, answer: str, status: str) -> str | None:
        """Write the audit event. A failure to audit is logged but never breaks the answer."""
        request = prepared.request
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
