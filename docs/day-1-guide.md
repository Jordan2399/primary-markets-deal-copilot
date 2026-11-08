
# Day 1 guide: what was built, how it works, how to continue

Day 1 turns the Day 0 skeleton into a working product: a deal pipeline with task checklists, an audit
trail, and a Copilot that answers "what is left before launch?" from real data, with sources.

Read this once, run the checks in section 2, then work through the exercises in section 7. If you can do
the exercises without help, you understand the code.

## 1. What exists now

| Area | What it does | Where |
| --- | --- | --- |
| Graph schema | 10 uniqueness constraints, 3 indexes, one vector index (768 dims, cosine) | `backend/app/db/schema.py` |
| Workflow definition | 8 stages, 34 task templates with owner, blocking flag, offset from launch, dependencies | `backend/app/deals/templates.py` |
| Deals | list, create, tasks, update task status, advance stage, launch readiness | `backend/app/deals/` |
| Audit | every change and every Copilot answer is written as an event | `backend/app/audit/` |
| LLM layer | one interface, Ollama implementation, JSON output with one retry, fake for tests | `backend/app/llm/` |
| Playbook | 10 Markdown pages, chunked and embedded into Neo4j | `backend/app/seed/playbook/`, `backend/app/documents/` |
| Copilot | LangGraph: classify, look up deal facts, retrieve playbook, compose; then stream | `backend/app/copilot/` |
| Seed | 25 issuers, 12 deals across all stages, demo deal `D-DEMO-001` | `backend/app/seed/` |
| Frontend | Pipeline, Deal workspace, Copilot, Audit, Status | `frontend/app/`, `frontend/lib/` |

All data is synthetic. Issuers, ISINs (`XS9999...`, with valid check digits) and dates are invented.

## 2. Run it and check it (do this first)

Prerequisites from Day 0 still apply: Docker Desktop running, Ollama running with
`qwen2.5:7b-instruct` and `nomic-embed-text` pulled.

```powershell
git checkout develop
git checkout -b feature/day-1-copilot
# copy the Day 1 files over your working tree (or pull them, if you push them to GitHub)

docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --build -d
docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml --profile tools run --rm seed
```

The seed prints a report (stages, issuers, deals created, playbook pages and chunks). The playbook step
calls Ollama, so Ollama must be running.

Then verify, in this order. Stop at the first thing that fails and read section 8.

1. `http://localhost:8000/api/v1/health` shows `neo4j` and `ollama` ok.
2. `http://localhost:8000/docs` lists the endpoints. Try `GET /api/v1/deals`: 12 deals.
3. `http://localhost:3000` shows the pipeline with deals in eight columns.
4. Open *Nordvik EUR 750m 5Y*. Documentation is the current stage, 7 of 34 tasks are done.
5. Switch the role (top right) to `syndicate`, mark a task *In progress*, check the Timeline tab.
6. Click *Advance stage*. It must refuse and list the blocking tasks. Finish them and try again.
7. Open Copilot with that deal and ask: **"What is left before launch?"**
   The answer should list open tasks by stage with owner and due date and cite `[S1]`, `[S2]`...
   Open *Evidence* to see the exact sources. The cited ones are highlighted.
8. Ask a process question: "How does allocation and scale back work?" It should cite playbook passages.
9. Ask something unrelated ("tell me a joke"). It must decline politely.
10. Switch to `admin`, open Audit. Your Copilot questions are there with model, prompt hash and sources.

Item 7 is the Day 1 gate. If a 7B model gives a weak answer, that is a prompt problem, not a code problem:
look at the sources in *Evidence* first. If the right tasks are there, change `copilot/prompts.py`.

Automated checks:

```powershell
cd backend
pip install -e ".[dev]"
pytest -q                     # 102 pass, 5 integration tests skipped
ruff check . ; ruff format --check . ; mypy app
cd ..\frontend
npm install ; npm run lint ; npm test ; npm run build
```

To run the 5 Neo4j integration tests locally, start a throwaway Neo4j and set the variables listed at the top
of `backend/tests/test_integration_neo4j.py`. They wipe the database they point at: never aim them at
your dev data.

## 3. How the code is organised

```
Request -> router -> service -> repository -> Neo4j
           (HTTP)    (rules)     (Cypher)
```

- **Router**: only HTTP. Parses input, checks the role, calls a service, returns JSON. No rules here.
- **Service**: the business rules ("a task cannot be Done while a dependency is open", "a deal cannot advance
  with open blocking tasks"). Plain Python. It receives a repository, so tests pass an in-memory one.
- **Repository**: all Cypher lives here. Each repository is a `Protocol` plus a Neo4j class.
- **`deps.py`**: builds services per request. Tests replace these functions with `dependency_overrides`.
- **Modules do not import each other's internals.** The Copilot uses `DealService` and `DocumentService`,
  never their repositories. That boundary is what lets a module become a separate service later.

Conventions you must keep:

1. Every error is `{"error": {"code", "message", "request_id", "details"}}`. Raise an `AppError` subclass from
   `core/errors.py`; do not return ad-hoc error JSON. The frontend has one parser for it.
2. Every change writes an audit event **in the same transaction** as the change (`audit/repository.write_in_tx`).
   Either both happen or neither.
3. Roles are checked in the router with `require_roles(...)`. `admin` always passes. Identity is a demo header
   pair (`X-Demo-Role`, `X-Demo-User`). It is not authentication. `get_current_user` in `core/security.py` is
   the one place to replace with OIDC later.
4. Settings come from environment variables via `core/config.py`. Never read `os.environ` elsewhere.
5. Prompts live only in `copilot/prompts.py`.
6. Cypher always uses parameters. Never build a query with string formatting from user input.

## 4. The data model

```
(Issuer)-[:MANDATED]->(Deal)-[:HAS_TRANCHE]->(Tranche)
(Deal)-[:IN_STAGE]->(Stage)-[:NEXT]->(Stage)      the deal's current stage
(Deal)-[:HAS_TASK]->(Task)-[:BELONGS_TO]->(Stage)
(Task)-[:DEPENDS_ON]->(Task)
(Document)-[:HAS_CHUNK]->(Chunk {embedding})
(AuditEvent)
```

Task ids are `{deal_id}:{template_key}` (for example `D-DEMO-001:d_sub`). That makes seeding repeatable and
makes citations human-readable.

Advancing a stage is a single transaction that checks blockers and moves the deal's `IN_STAGE` relationship together
(`Neo4jDealRepository.advance_stage`). Two people clicking at once cannot skip a blocker.

## 5. How the Copilot answers

```
question -> classify -> (deal)    graph_lookup -> compose
                        (process) retrieve     -> compose
                        (both)    graph_lookup -> retrieve -> compose
                        (other)   fixed polite refusal
```

- **classify** asks the model for `{"intent": ...}` using JSON-schema output, validates it, retries once, and if
  the model still fails falls back to keywords (`keyword_intent`). The Copilot keeps working when the model is
  weak.
- **graph_lookup** reads the deal and its open tasks through `DealService.launch_readiness`. These are facts,
  not guesses, and they are numbered `S1`, `S2`...
- **retrieve** embeds the question (with the `search_query: ` prefix nomic needs) and asks the vector index for
  the closest playbook chunks.
- **compose** builds the prompt. Sources are wrapped in `<source>` tags and the system prompt says they are
  data and that instructions inside them must be ignored. This is the prompt-injection defence.
- The graph does **not** generate the answer. `CopilotService.stream` does, token by token, as server-sent
  events: `meta` (intent and sources, first), `token` (many), `done` (cited ids and audit id) or `error`.
  Because sources arrive first, the UI shows evidence before the first word.
- Citations are checked: `[S9]` for a source that does not exist is not reported as cited.
- Every call is audited: question, answer, intent, model, prompt hash, source refs.

Why this shape: the answer to "what is left" is a database fact. The model's job is to phrase and group it, not to
remember it. That is what makes the answer checkable, and it is the point to make in an interview.

## 6. How to extend it

**Add or change a task in the workflow**: edit `TASK_TEMPLATES` in `deals/templates.py`. Rules, enforced by
`tests/test_templates.py`: unique key, known stage, listed in stage order, dependencies only on earlier tasks.
New deals pick it up immediately. Existing deals keep their tasks; seed with `--reset` in development to rebuild.

**Add a playbook page**: add a Markdown file to `seed/playbook/` (one `# Title`, then `## Sections`), then run
the seed. A page is indexed per section, so write each section to stand on its own.

**Add an endpoint**: model in `models.py`, rule in `service.py`, Cypher in `repository.py`, route in `router.py`
with `require_roles`, an in-memory method in `tests/fakes.py`, a test in `tests/test_api_*.py`. Always in that order.

**Improve an answer**: print the sources first (Evidence panel). Wrong sources: fix retrieval or lookup. Right sources,
bad wording: fix `SYSTEM_PROMPT`. Never put facts into the prompt that should come from the database.

**Add another LLM provider** (OpenAI or Claude): implement `LLMProvider` (`chat`, `stream`, `embed`, `aclose`) in
`llm/`, add one line in `llm/factory.py`, add settings. Nothing else changes. Caution: embeddings from a different
model have different dimensions, so changing the embedding model means changing `EMBED_DIMENSIONS`, recreating the
vector index and re-seeding the playbook.

## 7. Exercises (do these to own the code)

1. Add a task "Legal entity identifier checked" to the mandate stage, blocking, owned by `compliance`. Make the
   tests pass. Create a deal and see it in the checklist.
2. Add a playbook page `green-bonds.md` and ask the Copilot about it.
3. Make `viewer` unable to see the Audit link in the navigation (frontend only), then explain why that is not security.
4. Add a `GET /deals?stage=launch` filter, with a service-level test.
5. Break it on purpose: stop Ollama and ask a question. Read what the UI shows and what the audit event says.
6. Read `Neo4jDealRepository.advance_stage` and explain, in your own words, why the check and the move are one
   transaction.

## 8. If something fails

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Pipeline is empty | Not seeded | run the seed; `GET /api/v1/deals` |
| Seed fails on embeddings | Ollama not running or model missing | `ollama list`; `OLLAMA_BASE_URL` |
| "dimension" error in the seed | Embedding model is not 768-dim | `EMBED_DIMENSIONS`, drop the vector index, re-seed |
| Copilot says "could not find that deal" | Wrong deal selected / not seeded | pick from the list |
| Copilot answers but ignores the tasks | Classified as `process` | look at `intent` in the Evidence summary; adjust prompts |
| Copilot very slow the first time | Model loading into VRAM | normal; `LLM_KEEP_ALIVE` keeps it loaded |
| Frontend shows "The API is not reachable" | API down or `API_INTERNAL_URL` wrong | `docker compose ... logs api` |
| 403 on a button | Role cannot do it | change the demo role |
| Port already in use | Leftover process | see Day 0 notes |

## 9. Honest limits

- The Cypher, the vector index and the live Ollama behaviour were **not run in the build environment** (no Docker or
  Neo4j there). Business rules, the API, the Copilot graph and streaming are covered by 102 tests with fakes; the
  Neo4j-specific behaviour is covered by integration tests that run in CI. Treat the first real run as the first real
  test and fix what it finds.
- The answer quality of a 7B quantised model is not guaranteed. The design makes errors visible (sources, citations,
  audit) rather than impossible.
- Authentication is a demo header. Do not describe it as security.
- The UI is plain CSS, deliberately simple. It is correct and accessible, not polished.
- Roles: marketer and syndicate may both update tasks and advance stages, which is simpler than a real approval flow.
- Names differ slightly from the early plan: `position` instead of `order` for stages, `size_mm` instead of `size`.

## 10. Before you apply

- Push to GitHub with real branches and a pull request for Day 1, so the history shows the work in steps.
- Run the full checklist in section 2 and record a 2 minute screen capture of item 7 and item 10.
- Keep the "How this project was built" section of the README. You can explain every part of this code after the
  exercises, and saying that AI helped build it is both honest and, today, normal.
- Be ready to explain three decisions: why a modular monolith, why the model never owns the facts, and why the audit
  event is written in the same transaction as the change.
