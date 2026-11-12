# Day 2 guide: order book, allocation, term sheets

Day 2 adds the three things a primary markets desk does between "launch" and "booking":
watch the order book, allocate the bonds, and check the term sheet against the booking record.
All data is synthetic.

## 1. What exists now

| Area | What it does | Where |
| --- | --- | --- |
| Investors | 150 invented investors in 6 types (asset manager, insurer, pension fund, bank treasury, official institution, hedge fund) | `backend/app/investors/` |
| Order book | Simulated orders in waves, metrics (cover, ladder, timeline, mix) and anomaly rules | `backend/app/orderbook/` |
| Allocation | Rule-based engine, preview, proposal, four-eyes approval, explanation | `backend/app/allocation/` |
| Term sheets | Text/PDF reading, extraction (model + rules), code validators, booking diff | `backend/app/termsheets/` |
| Frontend | Order book, Allocation, Term sheets pages, SVG charts | `frontend/app/{orderbook,allocation,termsheets}/`, `frontend/components/Charts.tsx` |

Amounts are in whole thousands ("k"), minimum denomination and increment 100k.

## 2. Run it and check it

```bat
git checkout develop
git checkout -b feature/day-2-orderbook-allocation
docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --build -d
docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml --profile tools run --rm seed
```

Run the seed again: it is safe, and it now also loads the 150 investors and the order books of the demo deals.

Demo deals: `D-2026-007` (Book building), `D-2026-008` (Pricing), `D-2026-009` (Allocation).

Verify in this order:

1. **Order book**: role `syndicate`, pick D-2026-007. Cover, ladder, timeline and anomalies show. Click *Simulate new book* with another seed: numbers change, the book is replaced.
2. **Anomalies**: each flagged order says whether it is excluded or only flagged for review.
3. **Allocation** (the Day 2 gate): pick D-2026-009. The sum check must read "Sum check OK" with allocated equal to deal size. Change the final spread and watch the table recompute; allocated must still equal the deal size while the book is oversubscribed.
4. Click *Propose allocation*, then switch to role `approver`, open the proposal, *Approve*. As `syndicate` or `admin` the person who proposed cannot approve it (403, four-eyes).
5. **Term sheets** (the second gate): pick D-2026-008, *Load sample (with errors)*, *Extract and validate*. At least one row shows a red **MISMATCH**. *Load sample (matches booking)* gives all green.
6. Stop Ollama and repeat step 5. Extraction falls back to rules ("fixed rules (no model available)") and still works.

Automated:

```bat
cd backend
pip install -e ".[dev]" -c constraints.txt
pytest -q               # 959 pass, 9 integration tests skipped without Neo4j
ruff check . & ruff format --check . & mypy app
cd ..\frontend
npm install & npm run lint & npm test & npm run build
```

## 3. The rules

### Order book anomalies (`orderbook/anomalies.py`)
Rules run in code, not in the model: `duplicate` (same investor twice), `after_close` (placed after the book closed), `exceeds_deal_size` (order larger than the deal) and `ticket_zscore` (ticket far above the investor's usual size). Each finding says whether it **excludes** the order from allocation or only **flags** it for review.

### Allocation (`allocation/engine.py`)
Pure integer arithmetic. The docstring at the top of the file is the specification.

1. Eligible: not excluded, and `limit_bp <= final spread` (a limit is the widest spread the investor accepts).
2. Priority score = 2 x type points + timing points + participation points, maximum 10. Band 1 at 8+, band 2 at 6-7, band 3 below.
3. Bands are served in order. A band that fits is filled; the band that does not fit is scaled back pro rata, lower bands get nothing.
4. Rounding is in 100k increments: round down, then hand out the leftover increments by largest remainder. The total matches exactly.
5. Status: oversubscribed, fully covered, undersubscribed.

The model **never** produces a number. It only writes the explanation from the engine's result, and a fixed template replaces it when the model is unavailable or its text fails a check. The UI shows which one wrote it.

Four-eyes: `propose` stores a proposal; `approve` refuses when approver equals proposer. The audit event is written in the same transaction.

### Term sheets (`termsheets/`)
Extraction asks the model for a typed record, then fills gaps with regular expressions (`llm+rules`) or uses rules only when the model fails (`rules`). Then plain code decides:

- Validators (`validate.py`): required fields, ISIN format and check digit, ISIN present in the source text (catches invented values), currency allowed, size range, coupon range, maturity after issue, format allowed.
- Booking diff: per field `match`, `mismatch`, `missing_in_term_sheet`, `missing_in_booking`.

## 4. Data model additions

```
(Investor {id, name, type, region})
(Deal)-[:HAS_ORDER]->(Order {id, amount_k, limit_bp, placed_at, flags})-[:BY]->(Investor)
(Deal)-[:HAS_ALLOCATION]->(Allocation {id, state, final_spread_bp, lines_json, explanation})
(Deal)-[:HAS_DOCUMENT]->(Document)   term sheets, text stored, not chunked or embedded
```

## 5. Endpoints

| Method and path | Roles |
| --- | --- |
| `GET /deals/{id}/orderbook`, `/orderbook/anomalies` | syndicate, approver (admin always) |
| `POST /deals/{id}/orderbook/simulate` | syndicate (admin always) |
| `GET /deals/{id}/allocation/preview?final_spread_bp=` | syndicate, approver (admin always) |
| `POST /deals/{id}/allocation/propose` | syndicate (admin always) |
| `POST /deals/{id}/allocation/approve?proposal_id=` | approver (admin always, but not on its own proposal) |
| `GET /deals/{id}/allocation`, `GET /allocation/{id}` | syndicate, approver (admin always) |
| `POST /documents/extract`, `POST /documents/{id}/validate` | any demo user |
| `GET /deals/{id}/termsheet-sample?variant=good\|bad` | any demo user |

The order book and allocation work only for deals at Book building or later.

## 6. Exercises

1. Change the type points so hedge funds get 0. Run `pytest tests/test_allocation_engine.py`; find the test that now fails and decide whether the test or the rule is right.
2. Add a validator "coupon must be a multiple of 0.125". Test it with a good and a bad term sheet.
3. Add an anomaly rule "more than 3 orders from one investor type within one minute".
4. Read `scale_back` and prove by hand, with three orders of 100, 100, 100 and 250 available, that the result sums to 250.
5. Explain why the engine takes `EngineOrder` and not the database `Order`.
6. Add a `viewer` read-only summary of cover ratio only. Which layers change?

## 7. If something fails

| Symptom | Likely cause |
| --- | --- |
| Order book says no orders | Seed not re-run, or deal is before Book building |
| 403 on Approve | You proposed it; switch role/user (four-eyes) |
| 409 on preview/propose | Deal is before Book building, or the book is empty (simulate one) |
| 409 on approve | The proposal was already approved or changed by someone else |
| Term sheet upload 400 | File over 2 MB, wrong type, or PDF without text (scanned) |
| Extraction says "fixed rules" | Ollama unreachable, expected fallback |

## 8. Honest limits

- The Day 2 Cypher (Order, Allocation, Document) and the real model's extraction and wording were **not run** in the build environment (no Neo4j, Ollama or Docker). Logic, API and fakes are covered by tests; the 9 integration tests (CI, or locally against a throwaway Neo4j) cover the Cypher. Treat your first run as the first real test.
- Allocation amounts are computed, not editable by hand. A real desk adjusts manually; here that is a deliberate scope cut.
- The allocation rules are a simplified, invented policy for the demo. They are not any bank's policy.
- Term sheet text is stored but not chunked or embedded, so the Copilot cannot search it yet.
- Orders are simulated. Real order flow would arrive from a bookrunner platform.
