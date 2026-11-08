from datetime import date, timedelta

from tests.conftest import Env
from tests.fakes import add_deal

MARKETER = {"X-Demo-Role": "marketer", "X-Demo-User": "mia"}
SYNDICATE = {"X-Demo-Role": "syndicate"}
ADMIN = {"X-Demo-Role": "admin"}


def payload(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "issuer_id": "ISS-002",
        "name": "Aurelia EUR 500m 10Y",
        "currency": "EUR",
        "size_mm": 500,
        "tenor_years": 10,
        "format": "Domestic",
        "launch_date": (date.today() + timedelta(days=20)).isoformat(),
    }
    data.update(overrides)
    return data


async def test_reference_data(env: Env) -> None:
    stages = env.client.get("/api/v1/stages").json()
    assert [s["code"] for s in stages][:2] == ["mandate", "documentation"]
    assert len(env.client.get("/api/v1/issuers").json()) == 2


async def test_create_and_read_a_deal(env: Env) -> None:
    created = env.client.post("/api/v1/deals", json=payload(), headers=MARKETER)
    assert created.status_code == 201, created.text
    deal_id = created.json()["id"]
    assert env.client.get(f"/api/v1/deals/{deal_id}").json()["tasks_total"] == 34
    assert len(env.client.get("/api/v1/deals").json()) == 1
    tasks = env.client.get(f"/api/v1/deals/{deal_id}/tasks").json()
    assert len(tasks) == 34


async def test_viewer_cannot_create_a_deal(env: Env) -> None:
    response = env.client.post("/api/v1/deals", json=payload())
    assert response.status_code == 403
    body = response.json()["error"]
    assert body["code"] == "forbidden"
    assert body["request_id"]


async def test_validation_errors_use_the_standard_shape(env: Env) -> None:
    response = env.client.post("/api/v1/deals", json=payload(size_mm=1), headers=MARKETER)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unknown_role_is_a_bad_request(env: Env) -> None:
    response = env.client.post("/api/v1/deals", json=payload(), headers={"X-Demo-Role": "wizard"})
    assert response.status_code == 400
    assert "Unknown role" in response.json()["error"]["message"]


async def test_unknown_deal_is_404(env: Env) -> None:
    response = env.client.get("/api/v1/deals/D-NOPE")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_task_update_and_dependency_conflict(env: Env) -> None:
    await add_deal(env.repo, stage_code="documentation", done_in_stage=0)
    blocked = env.client.patch(
        "/api/v1/tasks/D-DEMO-001:d_terms", json={"status": "DONE"}, headers=SYNDICATE
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["details"]["open_dependencies"]
    ok = env.client.patch(
        "/api/v1/tasks/D-DEMO-001:d_prospectus", json={"status": "DONE"}, headers=SYNDICATE
    )
    assert ok.status_code == 200
    assert ok.json()["status"] == "DONE"


async def test_viewer_cannot_update_tasks(env: Env) -> None:
    await add_deal(env.repo)
    response = env.client.patch("/api/v1/tasks/D-DEMO-001:d_sub", json={"status": "DONE"})
    assert response.status_code == 403


async def test_advance_flow_and_timeline(env: Env) -> None:
    await add_deal(env.repo)
    blocked = env.client.post("/api/v1/deals/D-DEMO-001/advance", headers=SYNDICATE)
    assert blocked.status_code == 409
    for key in ("d_sub", "d_opinions"):
        env.client.patch(
            f"/api/v1/tasks/D-DEMO-001:{key}", json={"status": "DONE"}, headers=SYNDICATE
        )
    advanced = env.client.post("/api/v1/deals/D-DEMO-001/advance", headers=SYNDICATE)
    assert advanced.status_code == 200
    assert advanced.json()["stage_code"] == "pre_marketing"
    actions = [e["action"] for e in env.client.get("/api/v1/deals/D-DEMO-001/timeline").json()]
    assert actions[0] == "deal.advance"
    assert "task.update" in actions and "deal.create" in actions


async def test_audit_log_is_admin_only(env: Env) -> None:
    await add_deal(env.repo)
    assert env.client.get("/api/v1/audit", headers=MARKETER).status_code == 403
    response = env.client.get("/api/v1/audit", headers=ADMIN)
    assert response.status_code == 200
    assert response.json()[0]["action"] == "deal.create"


async def test_every_response_has_a_request_id(env: Env) -> None:
    response = env.client.get("/api/v1/stages", headers={"X-Request-ID": "abc-123"})
    assert response.headers["x-request-id"] == "abc-123"
