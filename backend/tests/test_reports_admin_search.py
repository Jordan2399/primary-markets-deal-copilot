"""Reports (roll-ups and CSV), the admin console and the global search, via the API."""

from app.llm.fake import FakeLLM
from tests.conftest import Env, build_env
from tests.fakes import add_deal

SYNDICATE = {"X-Demo-Role": "syndicate", "X-Demo-User": "demo.syndicate"}
APPROVER = {"X-Demo-Role": "approver", "X-Demo-User": "demo.approver"}
MARKETER = {"X-Demo-Role": "marketer"}
VIEWER = {"X-Demo-Role": "viewer"}
ADMIN = {"X-Demo-Role": "admin"}
DEAL = "D-DEMO-001"


async def booked(env: Env) -> None:
    await add_deal(env.repo, stage_code="book_building", done_in_stage=0)
    response = env.client.post(
        f"/api/v1/deals/{DEAL}/orderbook/simulate",
        json={"seed": 1, "target_cover": 3.0, "anomalies": 0},
        headers=SYNDICATE,
    )
    assert response.status_code == 200, response.text


# ------------------------------------------------------------------ reports


def test_overview_is_empty_but_valid_without_deals() -> None:
    env = build_env(FakeLLM())
    body = env.client.get("/api/v1/reports/overview", headers=VIEWER).json()
    assert body["kpis"]["active_deals"] == 0
    assert body["kpis"]["avg_cover"] is None
    assert len(body["activity"]) == 14  # a full two weeks, even with no events


async def test_overview_rolls_up_a_book_and_an_allocation() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    book = env.client.get(f"/api/v1/deals/{DEAL}/orderbook", headers=SYNDICATE).json()
    demand = book["metrics"]["total_demand_k"]

    before = env.client.get("/api/v1/reports/overview", headers=MARKETER).json()
    row = before["books"][0]
    assert row["orders"] == len(book["orders"]) and row["demand_k"] == demand
    assert row["cover"] == round(demand / (row["size_mm"] * 1000), 2)
    assert before["kpis"]["in_market"] == 1 and before["kpis"]["orders"] == row["orders"]
    assert before["kpis"]["pending_approvals"] == 0
    assert abs(sum(m["share_pct"] for m in before["mix_by_type"]) - 100) < 0.2
    assert sum(m["demand_k"] for m in before["mix_by_region"]) == sum(
        m["demand_k"] for m in before["mix_by_type"]
    )

    # A proposal waits for approval and shows up in the counts.
    proposed = env.client.post(
        f"/api/v1/deals/{DEAL}/allocation/propose", json={}, headers=SYNDICATE
    )
    assert proposed.status_code == 201, proposed.text
    after = env.client.get("/api/v1/reports/overview", headers=MARKETER).json()
    assert after["kpis"]["pending_approvals"] == 1
    assert after["books"][0]["allocation_state"] == "PROPOSED"
    assert after["books"][0]["allocated_k"] > 0
    # The proposal wrote audit events, so today has activity and the top actions list is filled.
    assert after["activity"][-1]["events"] > 0 and after["top_actions"]


async def test_csv_download_is_recorded_and_safe() -> None:
    env = build_env(FakeLLM())
    await add_deal(env.repo, stage_code="book_building", done_in_stage=0)
    env.repo._deals[DEAL]["name"] = '=HYPERLINK("http://evil")'  # a name that would be a formula
    response = env.client.get("/api/v1/reports/pipeline.csv", headers=MARKETER)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    text = response.content.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("Deal ID,Deal,Issuer")
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text
    events = env.client.get("/api/v1/audit?action=report", headers=ADMIN).json()
    assert any(e["action"] == "report.export" for e in events)


# ------------------------------------------------------------------ admin


def test_admin_overview_is_admin_only() -> None:
    env = build_env(FakeLLM())
    for headers in (VIEWER, MARKETER, SYNDICATE, APPROVER):
        assert env.client.get("/api/v1/admin/overview", headers=headers).status_code == 403
    body = env.client.get("/api/v1/admin/overview", headers=ADMIN).json()
    assert {r["role"] for r in body["roles"]} == {
        "viewer",
        "marketer",
        "syndicate",
        "approver",
        "admin",
    }
    assert all("password" not in u for u in body["users"])


# ------------------------------------------------------------------ search


async def test_search_finds_deals_and_hides_investors_from_viewers() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    name = env.repo._deals[DEAL]["name"]
    hits = env.client.get(f"/api/v1/search?q={name[:4].lower()}", headers=MARKETER).json()
    assert hits["deals"] and hits["deals"][0]["id"] == DEAL

    investor = env.client.get("/api/v1/investors?page_size=1", headers=MARKETER).json()["items"][0]
    found = env.client.get(f"/api/v1/search?q={investor['name'][:5]}", headers=MARKETER).json()
    assert any(i["id"] == investor["id"] for i in found["investors"])
    assert (
        env.client.get(f"/api/v1/search?q={investor['name'][:5]}", headers=VIEWER).json()[
            "investors"
        ]
        == []
    )


def test_search_needs_a_query() -> None:
    env = build_env(FakeLLM())
    assert env.client.get("/api/v1/search", headers=VIEWER).status_code == 422
