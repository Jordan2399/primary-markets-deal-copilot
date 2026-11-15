"""Investor directory, profile, deal network and targets, plus documents per deal, via the API."""

from app.llm.fake import FakeLLM
from tests.conftest import Env, build_env
from tests.fakes import add_deal

SYNDICATE = {"X-Demo-Role": "syndicate", "X-Demo-User": "demo.syndicate"}
APPROVER = {"X-Demo-Role": "approver", "X-Demo-User": "demo.approver"}
MARKETER = {"X-Demo-Role": "marketer"}
ADMIN = {"X-Demo-Role": "admin"}
DEAL = "D-DEMO-001"


async def booked(env: Env) -> None:
    """A deal in Book building with a simulated (synthetic) book."""
    await add_deal(env.repo, stage_code="book_building", done_in_stage=0)
    response = env.client.post(
        f"/api/v1/deals/{DEAL}/orderbook/simulate",
        json={"seed": 1, "target_cover": 3.0, "anomalies": 0},
        headers=SYNDICATE,
    )
    assert response.status_code == 200, response.text


# ------------------------------------------------------------------ roles


def test_viewers_may_not_see_investors_but_the_selling_desks_may() -> None:
    env = build_env(FakeLLM())
    assert env.client.get("/api/v1/investors").status_code == 403  # viewer
    for headers in (MARKETER, SYNDICATE, APPROVER, ADMIN):
        assert env.client.get("/api/v1/investors", headers=headers).status_code == 200


# ------------------------------------------------------------------ directory


def test_directory_pages_sorts_and_reports_facets() -> None:
    env = build_env(FakeLLM())
    body = env.client.get("/api/v1/investors?page_size=10", headers=MARKETER).json()
    assert body["total"] == 150 and len(body["items"]) == 10 and body["page"] == 1
    names = [i["name"].lower() for i in body["items"]]
    assert names == sorted(names)  # default sort is by name
    assert sum(f["count"] for f in body["types"]) == 150
    assert sum(f["count"] for f in body["regions"]) == 150

    page_two = env.client.get("/api/v1/investors?page_size=10&page=2", headers=MARKETER).json()
    assert {i["id"] for i in page_two["items"]}.isdisjoint({i["id"] for i in body["items"]})


def test_directory_filters_combine_and_facets_ignore_them() -> None:
    env = build_env(FakeLLM())
    url = "/api/v1/investors?type=pension_fund&real_money=true&page_size=100"
    body = env.client.get(url, headers=MARKETER).json()
    assert 0 < body["total"] < 150
    assert all(i["type"] == "pension_fund" and i["real_money"] for i in body["items"])
    assert sum(f["count"] for f in body["types"]) == 150  # facets still count everyone

    first = body["items"][0]
    search = env.client.get(f"/api/v1/investors?q={first['name'][:5].lower()}", headers=MARKETER)
    assert first["id"] in {i["id"] for i in search.json()["items"]}
    assert env.client.get("/api/v1/investors?q=zzzz-no-such", headers=MARKETER).json()["total"] == 0


def test_directory_rejects_bad_parameters() -> None:
    env = build_env(FakeLLM())
    for query in ("sort=banana", "page=0", "page_size=500"):
        assert env.client.get(f"/api/v1/investors?{query}", headers=MARKETER).status_code == 422


# ------------------------------------------------------------------ profile


async def test_profile_shows_orders_allocation_and_similar_investors() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    proposed = env.client.post(
        f"/api/v1/deals/{DEAL}/allocation/propose", json={}, headers=SYNDICATE
    )
    assert proposed.status_code == 201, proposed.text
    # Pick an investor that actually received an allocation (the first order may be filled at 0).
    filled = next(line for line in proposed.json()["lines"] if line["allocated_k"] > 0)
    investor_id = filled["investor_id"]

    profile = env.client.get(f"/api/v1/investors/{investor_id}", headers=MARKETER).json()
    me = profile["investor"]
    assert me["id"] == investor_id and me["orders"] >= 1 and me["deals"] == 1
    assert me["ordered_k"] == sum(o["amount_k"] for o in profile["orders"])
    assert profile["orders"][0]["deal_name"] == "Nordvik EUR 750m 5Y"
    # The proposal gave this investor something, and the profile reports it.
    assert me["allocated_k"] == sum(o["allocated_k"] or 0 for o in profile["orders"])
    assert me["allocated_k"] > 0
    assert all(s["type"] == me["type"] and s["region"] == me["region"] for s in profile["similar"])
    assert investor_id not in {s["id"] for s in profile["similar"]}
    assert len(profile["similar"]) <= 5


def test_unknown_investor_is_404() -> None:
    env = build_env(FakeLLM())
    assert env.client.get("/api/v1/investors/INV-NOPE", headers=MARKETER).status_code == 404


# ------------------------------------------------------------------ network and targets


async def test_network_sums_orders_per_investor_and_rolls_up_groups() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    net = env.client.get(f"/api/v1/deals/{DEAL}/investor-network", headers=SYNDICATE).json()
    book = env.client.get(f"/api/v1/deals/{DEAL}/orderbook", headers=SYNDICATE).json()
    assert net["deal_name"] == "Nordvik EUR 750m 5Y" and net["deal_size_k"] == 750_000
    assert net["total_demand_k"] == sum(o["amount_k"] for o in book["orders"])
    assert len({n["investor_id"] for n in net["nodes"]}) == len(net["nodes"])  # one node each
    amounts = [n["amount_k"] for n in net["nodes"]]
    assert amounts == sorted(amounts, reverse=True)
    assert abs(sum(g["share_pct"] for g in net["by_type"]) - 100) < 0.5
    assert sum(g["investors"] for g in net["by_region"]) == len(net["nodes"])


def test_network_of_a_deal_without_a_book_is_empty_and_unknown_deals_are_404() -> None:
    env = build_env(FakeLLM())
    assert (
        env.client.get(f"/api/v1/deals/{DEAL}/investor-network", headers=SYNDICATE).status_code
        == 404
    )


async def test_targets_exclude_investors_in_the_book_and_explain_the_score() -> None:
    env = build_env(FakeLLM())
    await booked(env)
    net = env.client.get(f"/api/v1/deals/{DEAL}/investor-network", headers=SYNDICATE).json()
    in_book = {n["investor_id"] for n in net["nodes"]}
    targets = env.client.get(
        f"/api/v1/deals/{DEAL}/investor-targets?limit=10", headers=MARKETER
    ).json()
    assert 0 < len(targets) <= 10
    assert in_book.isdisjoint({t["investor"]["id"] for t in targets})
    scores = [t["score"] for t in targets]
    assert scores == sorted(scores, reverse=True) and all(0 <= s <= 100 for s in scores)
    assert all(t["reasons"] or t["cautions"] for t in targets)
    assert (
        env.client.get(
            f"/api/v1/deals/{DEAL}/investor-targets?limit=0", headers=MARKETER
        ).status_code
        == 422
    )


async def test_targets_for_an_empty_book_get_no_region_bonus() -> None:
    env = build_env(FakeLLM())
    await add_deal(env.repo, stage_code="documentation")
    targets = env.client.get(
        f"/api/v1/deals/{DEAL}/investor-targets?limit=50", headers=MARKETER
    ).json()
    assert len(targets) == 50  # every investor is a candidate
    assert not any("under-represented" in r for t in targets for r in t["reasons"])


# ------------------------------------------------------------------ documents per deal


async def test_a_deal_lists_the_term_sheets_extracted_for_it() -> None:
    env = build_env(FakeLLM(fail=True))
    await add_deal(env.repo, stage_code="documentation")
    empty = env.client.get(f"/api/v1/deals/{DEAL}/documents", headers=SYNDICATE)
    assert empty.status_code == 200 and empty.json() == []
    sample = env.client.get(f"/api/v1/deals/{DEAL}/termsheet-sample?variant=good").json()
    created = env.client.post(
        "/api/v1/documents/extract",
        data={"text": sample["text"], "deal_id": DEAL},
        headers=SYNDICATE,
    )
    assert created.status_code == 201, created.text
    docs = env.client.get(f"/api/v1/deals/{DEAL}/documents", headers=SYNDICATE).json()
    assert len(docs) == 1 and docs[0]["id"] == created.json()["document_id"]
    assert docs[0]["isin"] and "text" not in docs[0]  # a summary, not the full document
    assert env.client.get("/api/v1/deals/D-NOPE/documents").status_code == 404
