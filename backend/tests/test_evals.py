"""The evaluation sets: the offline term sheet set must stay perfect (a regression guard), and the
Copilot scorer is checked on hand-made streams, so it can be trusted when the real run is made."""

from app.evals import copilot, termsheets

STREAM = [
    "event: meta",
    'data: {"intent": "deal", "model": "qwen2.5:7b-instruct", "sources": []}',
    "",
    "event: token",
    'data: {"text": "The deal is in "}',
    "",
    "event: token",
    'data: {"text": "Documentation [S1]."}',
    "",
    "event: done",
    'data: {"cited": ["S1"], "audit_id": "a1"}',
    "",
]


def test_term_sheet_set_is_all_correct_and_covers_six_languages() -> None:
    results = termsheets.run()
    assert termsheets.accuracy(results) == 1.0, termsheets.report(results)
    assert set(termsheets.by_language(results)) == {"en", "de", "fr", "es", "it", "nl"}


def test_a_wrong_value_is_reported_as_a_miss() -> None:
    case = {
        "id": "x",
        "language": "en",
        "text": "Issuer: Example Bank plc\nCurrency: EUR\n",
        "expected": {"currency": "USD", "issuer": "*", "isin": "*"},
    }
    result = termsheets.score_case(case)
    ok = {f.name: f.ok for f in result.fields}
    assert ok == {"currency": False, "issuer": True, "isin": False}  # "*" needs some value
    assert "expected 'USD'" in termsheets.report([result])


def test_stream_is_parsed_into_one_answer() -> None:
    answer = copilot.parse_sse(STREAM)
    assert answer.text == "The deal is in Documentation [S1]."
    assert answer.intent == "deal" and answer.cited == ["S1"] and answer.model.startswith("qwen")


def test_scoring_passes_a_good_answer_and_explains_each_failure() -> None:
    answer = copilot.parse_sse(STREAM)
    good = {
        "id": "g",
        "expect_any": ["documentation"],
        "expect_intent": ["deal"],
        "expect_citations": True,
    }
    assert copilot.score(good, answer).passed

    bad = {
        "id": "b",
        "expect_all": ["500"],
        "expect_any": ["pricing"],
        "expect_intent": ["process"],
        "forbid": ["documentation"],
        "expect_citations": False,
    }
    outcome = copilot.score(bad, answer)
    assert not outcome.passed and len(outcome.reasons) == 5


def test_an_error_event_fails_the_case() -> None:
    answer = copilot.parse_sse(["event: error", 'data: {"message": "model timed out"}'])
    outcome = copilot.score({"id": "e"}, answer)
    assert not outcome.passed and "model timed out" in outcome.reasons[0]


def test_every_copilot_case_has_a_check() -> None:
    cases = copilot.json.loads(copilot.DATA.read_text(encoding="utf-8"))
    assert len(cases) >= 10 and len({c["id"] for c in cases}) == len(cases)
    for c in cases:
        assert c["question"] and set(c) & {"expect_any", "expect_all", "expect_intent", "forbid"}


def test_deal_fact_questions_route_to_the_deal() -> None:
    """Size, currency and format questions are about the deal, not out of scope."""
    from app.copilot.prompts import keyword_intent

    assert keyword_intent("What is the size and currency of this deal?") in ("deal", "both")
    assert keyword_intent("Which format and currency does this deal use?") == "deal"
    assert keyword_intent("What is the weather in Berlin?") != "deal"
