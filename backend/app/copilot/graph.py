"""The Copilot as a LangGraph state machine.

    classify ──┬─(answer already known)──────────────► END
               ├─ deal ───► graph_lookup ──► compose ──► END
               ├─ process ► retrieve ──────► compose ──► END
               └─ both ───► graph_lookup ──► retrieve ──► compose ──► END

Nodes do one job each:
- classify:      decide the intent (LLM with JSON output, keyword fallback if the model fails)
- graph_lookup:  deterministic facts about the selected deal, read from Neo4j through DealService
- retrieve:      the closest playbook passages, found with the vector index
- compose:       build the final prompt (system prompt + history + question + numbered sources)

The graph does NOT call the LLM for the answer. The API streams the answer token by token
after the graph has finished (see copilot/service.py), so tool errors become clean HTTP errors
and the sources are known before the first word appears.
"""

from typing import Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel

from app.copilot.models import ChatRequest, Source
from app.copilot.prompts import (
    CLASSIFY_PROMPT,
    DEAL_NOT_FOUND_ANSWER,
    NEED_DEAL_ANSWER,
    OUT_OF_SCOPE_ANSWER,
    SYSTEM_PROMPT,
    keyword_intent,
    user_message,
)
from app.core.errors import NotFoundError
from app.deals.models import LaunchReadiness, Task
from app.deals.service import DealService
from app.documents.service import DocumentService
from app.llm.base import ChatMessage, LLMError, LLMProvider
from app.llm.json_output import chat_json

MAX_TASK_SOURCES = 25
MAX_SNIPPET_CHARS = 900
MAX_HISTORY_MESSAGES = 4


class Intent(BaseModel):
    intent: Literal["deal", "process", "both", "out_of_scope"]


class CopilotState(TypedDict, total=False):
    request: ChatRequest
    intent: str
    sources: list[Source]
    messages: list[ChatMessage]
    direct_answer: str | None


def _task_line(task: Task) -> str:
    due = task.due.isoformat() if task.due else "no due date"
    blocking = "blocking" if task.blocking else "not blocking"
    return (
        f"Task: {task.title} | stage: {task.stage_name} | owner: {task.owner_role} | "
        f"due: {due} | status: {task.status.value} | {blocking}"
    )


def _deal_source(readiness: LaunchReadiness, number: int) -> Source:
    deal = readiness.deal
    ready = "yes" if readiness.ready_to_launch else "no"
    snippet = (
        f"Deal: {deal.name} ({deal.id}) | issuer: {deal.issuer_name} | {deal.currency} "
        f"{deal.size_mm}m | current stage: {deal.stage_name} | launch date: {deal.launch_date} | "
        f"tasks done: {deal.tasks_done} of {deal.tasks_total} | open tasks before or at launch: "
        f"{readiness.open_before_launch} (blocking: {readiness.blocking_open_before_launch}) | "
        f"ready to launch: {ready}"
    )
    return Source(
        id=f"S{number}",
        type="deal",
        ref=deal.id,
        title=deal.name,
        snippet=snippet,
        meta={"stage": deal.stage_name},
    )


def _prioritise(tasks: list[Task]) -> list[Task]:
    """Most relevant first: open tasks before launch, blocking first, then by stage and due date."""
    return sorted(
        tasks,
        key=lambda t: (t.stage_position, not t.blocking, t.due.isoformat() if t.due else ""),
    )


def build_copilot_graph(deals: DealService, docs: DocumentService, llm: LLMProvider) -> Any:
    async def classify(state: CopilotState) -> dict[str, Any]:
        request = state["request"]
        intent: str
        try:
            result = await chat_json(
                llm,
                [
                    {"role": "system", "content": CLASSIFY_PROMPT},
                    {"role": "user", "content": request.message},
                ],
                Intent,
            )
            intent = result.intent
        except LLMError:
            intent = keyword_intent(request.message)

        if intent == "out_of_scope":
            return {"intent": intent, "direct_answer": OUT_OF_SCOPE_ANSWER, "sources": []}
        if intent in ("deal", "both") and not request.deal_id:
            return {"intent": intent, "direct_answer": NEED_DEAL_ANSWER, "sources": []}
        return {"intent": intent, "direct_answer": None, "sources": []}

    async def graph_lookup(state: CopilotState) -> dict[str, Any]:
        request = state["request"]
        assert request.deal_id is not None  # classify guarantees this
        try:
            readiness = await deals.launch_readiness(request.deal_id)
        except NotFoundError:
            return {"direct_answer": DEAL_NOT_FOUND_ANSWER}
        sources = [_deal_source(readiness, 1)]
        for task in _prioritise(readiness.open_tasks)[:MAX_TASK_SOURCES]:
            sources.append(
                Source(
                    id=f"S{len(sources) + 1}",
                    type="task",
                    ref=task.id,
                    title=task.title,
                    snippet=_task_line(task),
                    meta={
                        "stage": task.stage_name,
                        "owner": task.owner_role,
                        "status": task.status.value,
                    },
                )
            )
        return {"sources": sources}

    async def retrieve(state: CopilotState) -> dict[str, Any]:
        sources = list(state.get("sources", []))
        hits = await docs.search(state["request"].message)
        for hit in hits:
            sources.append(
                Source(
                    id=f"S{len(sources) + 1}",
                    type="playbook",
                    ref=hit.chunk_id,
                    title=f"{hit.doc_title} > {hit.heading}",
                    snippet=f"Playbook: {hit.doc_title} > {hit.heading}\n{hit.text[:MAX_SNIPPET_CHARS]}",
                    meta={"score": f"{hit.score:.2f}"},
                )
            )
        return {"sources": sources}

    async def compose(state: CopilotState) -> dict[str, Any]:
        request = state["request"]
        history: list[ChatMessage] = [
            {"role": item.role, "content": item.content[:1500]}
            for item in request.history[-MAX_HISTORY_MESSAGES:]
        ]
        messages: list[ChatMessage] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message(request.message, state.get("sources", []))},
        ]
        return {"messages": messages}

    def after_classify(state: CopilotState) -> str:
        if state.get("direct_answer"):
            return "end"
        return {"deal": "graph_lookup", "both": "graph_lookup", "process": "retrieve"}.get(
            state.get("intent", ""), "end"
        )

    def after_lookup(state: CopilotState) -> str:
        if state.get("direct_answer"):
            return "end"
        return "retrieve" if state.get("intent") == "both" else "compose"

    graph = StateGraph(CopilotState)
    graph.add_node("classify", classify)
    graph.add_node("graph_lookup", graph_lookup)
    graph.add_node("retrieve", retrieve)
    graph.add_node("compose", compose)
    graph.add_edge(START, "classify")
    graph.add_conditional_edges(
        "classify",
        after_classify,
        {"end": END, "graph_lookup": "graph_lookup", "retrieve": "retrieve"},
    )
    graph.add_conditional_edges(
        "graph_lookup", after_lookup, {"end": END, "retrieve": "retrieve", "compose": "compose"}
    )
    graph.add_edge("retrieve", "compose")
    graph.add_edge("compose", END)
    return graph.compile()
