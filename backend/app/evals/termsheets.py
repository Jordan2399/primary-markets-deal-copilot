"""Offline evaluation of the fixed term sheet rules.

No database, no model, no network: each case is a text with the values a person would read from
it. The score is the share of expected fields the rules got exactly right. A field that the rules
leave empty counts as a miss here, although in the application the model may still fill it, so
this number is the floor of what the application achieves.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.termsheets.rules import extract_with_rules

DATA = Path(__file__).parent / "data" / "termsheet_cases.json"
FIELDS = ("issuer", "isin", "currency", "size_mm", "coupon_pct", "maturity", "governing_law")


@dataclass
class FieldResult:
    name: str
    expected: Any
    actual: Any
    ok: bool


@dataclass
class CaseResult:
    id: str
    language: str
    fields: list[FieldResult] = field(default_factory=list)

    @property
    def correct(self) -> int:
        return sum(f.ok for f in self.fields)


def matches(expected: Any, actual: Any) -> bool:
    """ "*" means "any value, but something must be found". Everything else must be equal."""
    if expected == "*":
        return actual not in (None, "")
    return bool(expected == actual)


def score_case(case: dict[str, Any]) -> CaseResult:
    record = extract_with_rules(case["text"])
    got = record.model_dump(mode="json")
    result = CaseResult(case["id"], case["language"])
    for name, expected in case["expected"].items():
        actual = got.get(name)
        result.fields.append(FieldResult(name, expected, actual, matches(expected, actual)))
    return result


def load_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = json.loads(DATA.read_text(encoding="utf-8"))
    return cases


def run() -> list[CaseResult]:
    return [score_case(c) for c in load_cases()]


def accuracy(results: list[CaseResult]) -> float:
    total = sum(len(r.fields) for r in results)
    return sum(r.correct for r in results) / total if total else 0.0


def by_language(results: list[CaseResult]) -> dict[str, tuple[int, int]]:
    out: dict[str, list[int]] = {}
    for r in results:
        row = out.setdefault(r.language, [0, 0])
        row[0] += r.correct
        row[1] += len(r.fields)
    return {k: (v[0], v[1]) for k, v in sorted(out.items())}


def report(results: list[CaseResult]) -> str:
    """A Markdown report, ready to paste into docs/evaluation.md."""
    lines = ["| Case | Language | Fields right | Misses |", "|---|---|---|---|"]
    for r in results:
        misses = ", ".join(
            f"{f.name} (expected {f.expected!r}, got {f.actual!r})" for f in r.fields if not f.ok
        )
        lines.append(f"| {r.id} | {r.language} | {r.correct}/{len(r.fields)} | {misses or '-'} |")
    total = sum(len(r.fields) for r in results)
    right = sum(r.correct for r in results)
    lines += ["", f"**Overall: {right}/{total} fields right ({accuracy(results):.0%}).**", ""]
    lines += ["| Language | Fields right |", "|---|---|"]
    lines += [f"| {lang} | {a}/{b} |" for lang, (a, b) in by_language(results).items()]
    return "\n".join(lines)
