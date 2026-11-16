"""Evaluation of the Copilot against a RUNNING stack (API, Neo4j with the seed data, Ollama).

It signs in, asks each question in data/copilot_cases.json, reads the streamed answer and checks:
the intent the Copilot chose, words that must (or must not) appear, and whether the answer cites
its sources. It measures behaviour, not wording quality; read a few answers yourself as well.
"""

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

DATA = Path(__file__).parent / "data" / "copilot_cases.json"


@dataclass
class Answer:
    text: str = ""
    intent: str = ""
    model: str = ""
    cited: list[str] = field(default_factory=list)
    error: str | None = None
    seconds: float = 0.0


@dataclass
class CaseOutcome:
    id: str
    passed: bool
    reasons: list[str]
    answer: Answer


def parse_sse(lines: list[str]) -> Answer:
    """Turn the event stream into one Answer. Understands the meta, token, done and error events."""
    answer = Answer()
    event = ""
    for line in lines:
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data = json.loads(line[5:].strip())
            if event == "meta":
                answer.intent = data.get("intent", "")
                answer.model = data.get("model", "")
            elif event == "token":
                answer.text += data.get("text", "")
            elif event == "done":
                answer.cited = list(data.get("cited", []))
            elif event == "error":
                answer.error = data.get("message", "error")
    return answer


def score(case: dict[str, Any], answer: Answer) -> CaseOutcome:
    """Apply the case's checks. Every failed check adds a reason, so a failure explains itself."""
    reasons: list[str] = []
    text = answer.text.lower()
    if answer.error:
        reasons.append(f"error: {answer.error}")
    if "expect_intent" in case and answer.intent not in case["expect_intent"]:
        reasons.append(f"intent {answer.intent!r}, wanted one of {case['expect_intent']}")
    for needle in case.get("expect_all", []):
        if needle.lower() not in text:
            reasons.append(f"missing {needle!r}")
    if case.get("expect_any") and not any(n.lower() in text for n in case["expect_any"]):
        reasons.append(f"none of {case['expect_any']} found")
    for needle in case.get("forbid", []):
        if needle.lower() in text:
            reasons.append(f"must not contain {needle!r}")
    if "expect_citations" in case and bool(answer.cited) != case["expect_citations"]:
        reasons.append("cited sources" if answer.cited else "no citations")
    return CaseOutcome(case["id"], not reasons, reasons, answer)


def ask(client: httpx.Client, base: str, case: dict[str, Any]) -> Answer:
    started = time.monotonic()
    body: dict[str, Any] = {"message": case["question"]}
    if case.get("deal_id"):
        body["deal_id"] = case["deal_id"]
    with client.stream("POST", f"{base}/api/v1/copilot/chat", json=body, timeout=300) as response:
        response.raise_for_status()
        answer = parse_sse(list(response.iter_lines()))
    answer.seconds = time.monotonic() - started
    return answer


def run(base: str, username: str, password: str) -> list[CaseOutcome]:
    cases: list[dict[str, Any]] = json.loads(DATA.read_text(encoding="utf-8"))
    with httpx.Client() as client:
        login = client.post(
            f"{base}/api/v1/auth/login", json={"username": username, "password": password}
        )
        login.raise_for_status()
        client.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        return [score(c, ask(client, base, c)) for c in cases]


def _notes(outcome: CaseOutcome) -> str:
    """Reasons for a failed case plus what the Copilot actually said, so a failure can be diagnosed."""
    if outcome.passed:
        return "-"
    said = outcome.answer.error or outcome.answer.text
    snippet = " ".join(said.split())[:140].replace("|", "/")
    return f"{'; '.join(outcome.reasons)}; intent={outcome.answer.intent or '?'}; said: {snippet}"


def report(outcomes: list[CaseOutcome]) -> str:
    passed = sum(o.passed for o in outcomes)
    model = next((o.answer.model for o in outcomes if o.answer.model), "unknown")
    lines = [f"Model: `{model}`", "", "| Case | Result | Seconds | Notes |", "|---|---|---|---|"]
    for o in outcomes:
        lines.append(
            f"| {o.id} | {'pass' if o.passed else 'FAIL'} | {o.answer.seconds:.1f} | {_notes(o)} |"
        )
    lines += ["", f"**{passed}/{len(outcomes)} cases passed ({passed / len(outcomes):.0%}).**"]
    return "\n".join(lines)
