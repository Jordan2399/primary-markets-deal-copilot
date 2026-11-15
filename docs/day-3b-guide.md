# Day 3b: deal workspace and investor pages

Day 3b turns the deal page into a workspace with tabs and adds the investor side of the product:
a directory, investor profiles, an investor network graph for each deal, and a ranked "who to call
next" list. It is read-only: it adds no data and changes no existing behaviour.

## What you can do now

| Where | What |
|---|---|
| Deal page, header | Stage stepper, key figures, an "Advance stage" button that asks first and lists blockers |
| Deal page, tabs | Overview, Checklist, Order book, Allocation, Documents, Investors, Timeline. The open tab is in the address (`?tab=orderbook`). |
| `/investors` | Search, filter (type, region, account, ESG), sort and page through the 150 investors |
| `/investors/{id}` | Facts, orders and allocation per deal, similar investors |
| Deal page, Investors tab | Network graph of the book and the target list |
| Pipeline | Search and filter the board |
| Term sheet lab | `?deal=` preselects a deal; optional missing fields are grey, not red |

## New API endpoints (all read-only, roles: marketer, syndicate, approver, admin)

| Endpoint | Returns |
|---|---|
| `GET /investors?q=&type=&region=&real_money=&esg=&sort=&page=&page_size=` | One page of investors with activity totals, plus filter counts |
| `GET /investors/{id}` | The investor, its orders by deal and up to five similar investors |
| `GET /deals/{id}/investor-network` | Investors in the deal's book (orders summed per investor) with roll-ups by type and region |
| `GET /deals/{id}/investor-targets?limit=` | Investors NOT in the book, ranked by score with reasons and cautions |
| `GET /deals/{id}/documents` | Term sheets extracted for the deal (any signed-in role) |

Viewers get `403` on the investor endpoints and the pages explain why instead of showing an error.

## How the target score works

An investor not yet in the book earns up to 100 points (weights are constants in
`backend/app/investors/scoring.py`):

- real-money account: 30
- past participation, up to 20 deals: 25
- typical ticket between 1% and 10% of the deal size: 30 (less outside that band)
- region that has under 5% of the book's demand: 15 (not given while the book is empty)

Every score comes with plain-language reasons and cautions. It is a rule set, not a model: code
decides, and you can explain it line by line in an interview.

## The graph

`frontend/lib/network-layout.ts` is a pure function that turns the investors into coordinates:
one wedge per investor type, bigger orders closer to the deal and drawn bigger, filled circles for
real-money accounts. Nothing is random, so the picture is the same every time. The component only
draws it. A "Show as table" switch gives the same data as a table for keyboard and screen-reader
users. No chart library is used.

## Files

Backend (new): `investors/router.py`, `service.py`, `repository.py`, `scoring.py`,
`tests/test_investors_api.py`, `tests/test_investor_scoring.py`.
Backend (changed): `investors/models.py`, `deps.py`, `main.py`, `termsheets/{models,repository,service,router}.py`,
`tests/fakes.py`, `tests/conftest.py`, `tests/test_integration_neo4j.py`.

Frontend (new): `components/{Tabs,Skeleton,Toast,StageStepper,ConfirmDialog,InvestorNetwork}.tsx`,
`components/deal/{Overview,OrderBook,Allocation,Documents,Investors}Tab.tsx`,
`app/investors/page.tsx`, `app/investors/[id]/page.tsx`,
`lib/{network-layout,deal-tabs,use-load}.ts` and tests for the first two.
Frontend (changed): `app/deals/[id]/page.tsx` (rewritten), `app/page.tsx`, `app/termsheets/page.tsx`,
`app/globals.css`, `components/{AppShell,ui}.tsx`, `lib/{client,types,session-utils}.ts` and its test.

## Run and check

```
cd backend && pytest -q          # 1047 passed, integration tests skipped without Neo4j
cd frontend && npx tsc --noEmit && npx vitest run && npx next build
```

Then rebuild the images (see the README), sign in as `anna.syndicate`, open a deal at Book
building and try the tabs. The Cypher of the investor queries is exercised only by
`test_investor_queries_against_neo4j`, which runs when `TEST_NEO4J_URI` is set.

## Limits to know about

- The directory and profile load all orders in one query. That is fine for a few hundred orders; a
  real desk would page it in the database.
- The target score ignores sector, ESG fit and rating, because the synthetic data has no such
  link between investors and deals.
- The Documents tab lists term sheets; it does not preview them.
