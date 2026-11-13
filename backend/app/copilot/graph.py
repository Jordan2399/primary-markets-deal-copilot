"""The Copilot as a LangGraph state machine.

    rewrite ──► classify ──┬─(answer already known)──────────────► END
                           ├─ deal ───► graph_lookup ──► compose ──► END
                           ├─ process ► retrieve ──────► compose ──► END
                           └─ both ───► graph_lookup ──► retrieve ──► compose ──► END

Nodes do one job each:
- rewrite:       make a follow-up question stand on its own, using the conversation so far
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
    REWRITE_PROMPT,
    SYSTEM_PROMPT,
    keyword_intent,
    rewrite_input,
    user_message,
)
from app.core.errors import NotFoundError
from app.deals.models import LaunchReadiness, Task
from app.deals.service import DealService
from app.documents.service import DocumentService
from app.llm.base import ChatMessage, LLMError, LLMProvider
from app.llm.json_output import chat_json

MAX_TASK_SOURCES = 25  # at most this many task sources go to the model (keeps the prompt small)
MAX_SNIPPET_CHARS = 900  # playbook passages are cut to this length
MAX_HISTORY_MESSAGES = 4  # how many earlier messages the rewrite and the prompt may use


class Intent(BaseModel):
    """The shape the classify step asks the model to return (validated by pydantic)."""

    intent: Literal["deal", "process", "both", "out_of_scope"]


class Rewrite(BaseModel):
    """The shape the rewrite step asks the model to return."""

    standalone_question: str


class CopilotState(TypedDict, total=False):
    """The data passed from node to node. Each node returns only the keys it changes."""

    request: ChatRequest  # what the user sent, including server-loaded history
    question: str  # the question the later steps use; a follow-up is rewritten to stand alone
    intent: str  # deal, process, both or out_of_scope
    sources: list[Source]
    messages: list[ChatMessage]  # the final prompt, ready for the streaming step
    direct_answer: str | None  # set when no model answer is needed (out of scope, no deal...)


def _task_line(task: Task) -> str:
    """One task as a single readable line; this text is what the model sees as evidence."""
    due = task.due.isoformat() if task.due else "no due date"
    blocking = "blocking" if task.blocking else "not blocking"
    return (
        f"Task: {task.title} | stage: {task.stage_name} | owner: {task.owner_role} | "
        f"due: {due} | status: {task.status.value} | {blocking}"
    )


def _deal_source(readiness: LaunchReadiness, number: int) -> Source:
    """Evidence S<number> that summarises the deal itself (stage, dates, task counts, readiness)."""
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


MAX_REWRITE_CHARS = 500  # a rewritten question longer than this is treated as unusable


def build_copilot_graph(deals: DealService, docs: DocumentService, llm: LLMProvider) -> Any:
    """Wire the nodes into a compiled LangGraph. Services are passed in so tests can fake them."""

    async def rewrite(state: CopilotState) -> dict[str, Any]:
        """Turn a follow-up ("and who owns those?") into a question that stands on its own.

        Only runs when the conversation has earlier messages. If the model fails or returns
        something unusable, the original question is used, so a follow-up is never lost.
        """
        request = state["request"]
        # First question of a thread: nothing to resolve, skip the model call entirely.
        if not request.history:
            return {"question": request.message}
        # Only the last few turns matter for resolving words like 'it' or 'those'.
        recent = [(h.role, h.content) for h in request.history[-MAX_HISTORY_MESSAGES:]]
        try:
            result = await chat_json(
                llm,
                [
                    {"role": "system", "content": REWRITE_PROMPT},
                    {"role": "user", "content": rewrite_input(recent, request.message)},
                ],
                Rewrite,
            )
        except LLMError:
            return {"question": request.message}  # model down: fall back to the user's own words
        text = " ".join(result.standalone_question.split())
        # Accept the rewrite only if it is non-empty and not suspiciously long.
        if 0 < len(text) <= MAX_REWRITE_CHARS:
            return {"question": text}
        return {"question": request.message}

    async def classify(state: CopilotState) -> dict[str, Any]:
        """Decide what kind of question this is, and stop early when no model answer is needed."""
        request = state["request"]
        question = state.get("question", request.message)  # the rewritten question if there is one
        intent: str
        try:
            result = await chat_json(
                llm,
                [
                    {"role": "system", "content": CLASSIFY_PROMPT},
                    {"role": "user", "content": question},
                ],
                Intent,
            )
            intent = result.intent
        except LLMError:
            intent = keyword_intent(question)  # simple keyword rules when the model fails

        # Out of scope: answer with a fixed polite message, no model call.
        if intent == "out_of_scope":
            return {"intent": intent, "direct_answer": OUT_OF_SCOPE_ANSWER, "sources": []}
        # A deal question needs a selected deal; ask the user to pick one.
        if intent in ("deal", "both") and not request.deal_id:
            return {"intent": intent, "direct_answer": NEED_DEAL_ANSWER, "sources": []}
        return {"intent": intent, "direct_answer": None, "sources": []}

    async def graph_lookup(state: CopilotState) -> dict[str, Any]:
        """Load deterministic facts about the selected deal from the database as sources."""
        request = state["request"]
        assert request.deal_id is not None  # classify guarantees this
        try:
            readiness = await deals.launch_readiness(request.deal_id)
        except NotFoundError:
            return {"direct_answer": DEAL_NOT_FOUND_ANSWER}
        sources = [_deal_source(readiness, 1)]  # S1 is always the deal summary
        # Then the most relevant open tasks, each numbered S2, S3, ... so the model can cite them.
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
        """Add the closest playbook passages (vector search) after the deal sources."""
        sources = list(state.get("sources", []))
        hits = await docs.search(state.get("question", state["request"].message))
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
        """Assemble the final prompt: rules, recent history, then the question with its sources."""
        request = state["request"]
        history: list[ChatMessage] = [
            {"role": item.role, "content": item.content[:1500]}
            for item in request.history[-MAX_HISTORY_MESSAGES:]
        ]
        # The user's original wording is sent (not the rewrite) so the answer reads naturally;
        # the rewrite only steered classification and retrieval.
        messages: list[ChatMessage] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *history,
            {"role": "user", "content": user_message(request.message, state.get("sources", []))},
        ]
        return {"messages": messages}

    def after_classify(state: CopilotState) -> str:
        """Routing rule after classify: finish, look up the deal, or search the playbook."""
        if state.get("direct_answer"):
            return "end"
        return {"deal": "graph_lookup", "both": "graph_lookup", "process": "retrieve"}.get(
            state.get("intent", ""), "end"
        )

    def after_lookup(state: CopilotState) -> str:
        """After the deal lookup: 'both' also searches the playbook, otherwise go to compose."""
        if state.get("direct_answer"):
            return "end"
        return "retrieve" if state.get("intent") == "both" else "compose"

    # Build the graph: register the nodes, then draw the arrows between them.
    graph = StateGraph(CopilotState)
    graph.add_node("rewrite", rewrite)
    graph.add_node("classify", classify)
    graph.add_node("graph_lookup", graph_lookup)
    graph.add_node("retrieve", retrieve)
    graph.add_node("compose", compose)
    graph.add_edge(START, "rewrite")
    graph.add_edge("rewrite", "classify")
    # Conditional edges call a routing function and follow the arrow named by its return value.
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
