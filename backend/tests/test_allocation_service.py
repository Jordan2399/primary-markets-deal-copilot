"""Propose, explain and approve, including the four-eyes rule, through the API."""

from app.llm.fake import FakeLLM
from tests.conftest import Env, build_env
from tests.fakes import add_deal

SYNDICATE = {"X-Demo-Role": "syndicate", "X-Demo-User": "demo.syndicate"}
APPROVER = {"X-Demo-Role": "approver", "X-Demo-User": "demo.approver"}
ADMIN = {"X-Demo-Role": "admin", "X-Demo-User": "demo.admin"}
MARKETER = {"X-Demo-Role": "marketer"}


async def booked(env: Env, stage: str = "book_building") -> None:
    await add_deal(env.repo, stage_code=stage, done_in_stage=0)
    response = env.client.post(
        "/api/v1/deals/D-DEMO-001/orderbook/simulate",
        json={"seed": 1, "target_cover": 3.0, "anomalies": 4},
        headers=SYNDICATE,
    )
    assert response.status_code == 200, response.text


async def test_orderbook_endpoint_roles_and_content() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    assert env.client.get("/api/v1/deals/D-DEMO-001/orderbook").status_code == 403  # viewer
    assert env.client.get("/api/v1/deals/D-DEMO-001/orderbook", headers=MARKETER).status_code == 403
    book = env.client.get("/api/v1/deals/D-DEMO-001/orderbook", headers=APPROVER).json()
    assert book["metrics"]["cover_ratio"] > 2
    assert len(book["anomalies"]) >= 4
    flagged = [o for o in book["orders"] if o["flags"]]
    assert flagged
    anomalies = env.client.get(
        "/api/v1/deals/D-DEMO-001/orderbook/anomalies", headers=SYNDICATE
    ).json()
    assert {a["rule"] for a in anomalies} >= {"duplicate", "after_close"}


async def test_simulate_needs_the_syndicate_role_and_the_right_stage() -> None:
    env = build_env(FakeLLM())
    await add_deal(env.repo, stage_code="documentation")
    url = "/api/v1/deals/D-DEMO-001/orderbook/simulate"
    assert env.client.post(url, json={}, headers=APPROVER).status_code == 403
    early = env.client.post(url, json={}, headers=SYNDICATE)
    assert early.status_code == 409 and "Book building" in early.json()["error"]["message"]
    bad = env.client.post(url, json={"target_cover": 99}, headers=SYNDICATE)
    assert bad.status_code == 422


async def test_propose_returns_a_balanced_allocation_with_explanation() -> None:
    env = build_env(FakeLLM(chat_responses=["Band 1 was filled; later bands were scaled back."]))
    await booked(env)
    response = env.client.post(
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=SYNDICATE
    )
    assert response.status_code == 201, response.text
    proposal = response.json()
    assert proposal["state"] == "PROPOSED" and proposal["proposed_by"] == "demo.syndicate"
    assert proposal["total_allocated_k"] == proposal["deal_size_k"] == 750_000
    assert sum(line["allocated_k"] for line in proposal["lines"]) == 750_000
    assert proposal["explanation"].startswith("Band 1")
    assert proposal["explanation_source"] == "fake-model"
    event = env.repo.events[-1]
    assert (
        event.action == "allocation.propose" and event.model == "fake-model" and event.prompt_hash
    )


async def test_explanation_falls_back_to_a_template_when_the_model_is_down() -> None:
    env = build_env(FakeLLM(fail=True))
    await booked(env)
    proposal = env.client.post(
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=SYNDICATE
    ).json()
    assert proposal["explanation_source"] == "template"
    assert "eligible demand" in proposal["explanation"]
    assert env.repo.events[-1].model is None  # no model was used, so none is recorded


async def test_excluded_orders_receive_nothing() -> None:
    env = build_env(FakeLLM(chat_responses=["ok"]))
    await booked(env)
    proposal = env.client.post(
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=SYNDICATE
    ).json()
    excluded = [line for line in proposal["lines"] if line["note"].startswith("Excluded")]
    assert excluded and all(line["allocated_k"] == 0 for line in excluded)


async def test_preview_lets_the_spread_change_without_saving() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    base = "/api/v1/deals/D-DEMO-001/allocation/preview"
    wide = env.client.get(base, params={"final_spread_bp": 300}, headers=SYNDICATE).json()
    tight = env.client.get(base, params={"final_spread_bp": 1}, headers=SYNDICATE).json()
    assert wide["eligible_demand_k"] > tight["eligible_demand_k"]
    assert env.client.get("/api/v1/deals/D-DEMO-001/allocation", headers=SYNDICATE).json() == []


async def test_four_eyes_the_proposer_cannot_approve() -> None:
    env = build_env(FakeLLM(chat_responses=["ok"]))
    await booked(env)
    proposal = env.client.post(
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=SYNDICATE
    ).json()
    url = f"/api/v1/deals/D-DEMO-001/allocation/approve?proposal_id={proposal['id']}"

    assert env.client.post(url, headers=SYNDICATE).status_code == 403  # wrong role

    # An admin passes every role check, but if the admin proposed it, the admin cannot approve it.
    own = env.client.post(
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=ADMIN
    ).json()
    refused = env.client.post(
        f"/api/v1/deals/D-DEMO-001/allocation/approve?proposal_id={own['id']}", headers=ADMIN
    )
    assert refused.status_code == 403
    assert "Four-eyes" in refused.json()["error"]["message"]


async def test_a_different_approver_can_approve_once() -> None:
    env = build_env(FakeLLM(chat_responses=["ok"]))
    await booked(env)
    proposal = env.client.post(
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=SYNDICATE
    ).json()
    url = f"/api/v1/deals/D-DEMO-001/allocation/approve?proposal_id={proposal['id']}"
    approved = env.client.post(url, headers=APPROVER)
    assert approved.status_code == 200
    body = approved.json()
    assert body["state"] == "APPROVED" and body["approved_by"] == "demo.approver"
    assert env.repo.events[-1].action == "allocation.approve"
    assert env.repo.events[-1].details["proposed_by"] == "demo.syndicate"

    again = env.client.post(url, headers=APPROVER)
    assert again.status_code == 409


async def test_a_new_proposal_supersedes_the_open_one() -> None:
    env = build_env(FakeLLM(chat_responses=["one", "two"]))
    await booked(env)
    post = lambda: env.client.post(  # noqa: E731
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=SYNDICATE
    ).json()
    first, second = post(), post()
    states = {
        p["id"]: p["state"]
        for p in env.client.get("/api/v1/deals/D-DEMO-001/allocation", headers=APPROVER).json()
    }
    assert states == {first["id"]: "SUPERSEDED", second["id"]: "PROPOSED"}
    url = f"/api/v1/deals/D-DEMO-001/allocation/approve?proposal_id={first['id']}"
    assert env.client.post(url, headers=APPROVER).status_code == 409


async def test_approve_checks_the_deal_and_the_proposal_exist() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    url = "/api/v1/deals/D-DEMO-001/allocation/approve?proposal_id=ALLOC-NOPE"
    assert env.client.post(url, headers=APPROVER).status_code == 404
    assert env.client.get("/api/v1/allocation/ALLOC-NOPE", headers=APPROVER).status_code == 404


async def test_propose_needs_a_book() -> None:
    env = build_env(FakeLLM())
    await add_deal(env.repo, stage_code="book_building", done_in_stage=0)
    response = env.client.post(
        "/api/v1/deals/D-DEMO-001/allocation/propose", json={}, headers=SYNDICATE
    )
    assert response.status_code == 409 and "empty" in response.json()["error"]["message"]
