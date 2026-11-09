# Primary Markets Deal Copilot

A full-stack demo for bond primary markets: deal workflow, order book and allocation, term sheet
extraction and validation, and an investor appetite graph. It runs locally with open-source LLMs
(Ollama), a Neo4j graph database, a FastAPI backend and a Next.js frontend.

> **All data in this project is synthetic.** It uses no real client, investor or market data and
> connects to no bank system. It is a portfolio project, not a production banking system.

## Status

| Day | Scope | State |
| --- | --- | --- |
| 0 | Repo, Docker Compose (dev and prod), FastAPI health endpoint, Next.js status page, CI | **done** |
| 1 | Neo4j schema, seed data, deals and audit modules, LLM client, Lifecycle Copilot with sources, pipeline / workspace / Copilot / audit pages | **done** (see [docs/day-1-guide.md](docs/day-1-guide.md)) |
| 2 | Order book, allocation engine, term sheet extraction | planned |
| 3 | Investor graph, evaluation, polish, demo | planned |

## Architecture

```
Browser -> Next.js (3000) --/api proxy--> FastAPI (8000) -> Neo4j (7687)
                                               |
                                               +-> Ollama on the host GPU (11434)
```

Ollama runs natively on the host (not in Docker) so it can use the GPU. Containers reach it at
`http://host.docker.internal:11434`. Only the API talks to Neo4j and Ollama.

## Prerequisites (Windows)

- Docker Desktop (running)
- Ollama (installed natively), NVIDIA driver
- Git

## Quick start

1. Check the machine and pull the models (about 5 GB download the first time):

   ```powershell
   powershell -ExecutionPolicy Bypass -File scripts\check-env.ps1
   ```

   It prints GPU memory before and after loading the model, so you can see your real VRAM use.

2. Create your development environment file and set a password:

   ```powershell
   copy .env.dev.example .env.dev
   ```

3. Start the development stack:

   ```powershell
   docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml up --build
   ```

4. Load the synthetic data (needs Ollama running, for the playbook embeddings):

   ```powershell
   docker compose -p dealcopilot-dev --env-file .env.dev -f docker-compose.yml -f docker-compose.dev.yml --profile tools run --rm seed
   ```

   It is safe to run again: existing deals are skipped. Add `--reset` at the end to wipe and reload
   (development only).

5. Open:
   - Frontend: http://localhost:3000 (pipeline), `/copilot`, `/audit`, `/status`
   - API docs: http://localhost:8000/docs
   - API health: http://localhost:8000/api/v1/health
   - Neo4j Browser: http://localhost:7474 (user `neo4j`, password from `.env.dev`)

Try the Day 1 gate: open **Copilot**, choose *Nordvik EUR 750m 5Y*, ask
*"What is left before launch?"*. The answer must list the open tasks, and the *Evidence* panel shows
the exact sources. Use the role selector (top right) to try `marketer`, `syndicate` and `admin`.

The status page (`/status`) shows `ok` for both Neo4j and Ollama when everything is wired up. If Ollama shows
as unreachable from the containers, set the Windows environment variable `OLLAMA_HOST=0.0.0.0`,
restart Ollama, and allow it through the firewall for private networks only.

## Development and production separation

The two environments share the code but nothing else.

| | Development | Production |
| --- | --- | --- |
| Git branch | `develop` | `main` |
| Env file | `.env.dev` | `.env.prod` |
| Compose project | `dealcopilot-dev` | `dealcopilot-prod` |
| Ports (frontend / API) | 3000 / 8000 | 3100 / 8100 |
| Neo4j published | yes (7474, 7687) | no |
| Neo4j data volume | its own | its own |
| API reload on code change | yes | no |

Run production locally:

```powershell
copy .env.prod.example .env.prod   # then set a different, strong password
docker compose -p dealcopilot-prod --env-file .env.prod -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

Because each project name has its own containers, network and Neo4j volume, deleting or reseeding
the development database cannot touch production data.

### Branch workflow

- Work on feature branches, open pull requests into `develop`.
- Release by a pull request from `develop` into `main`, with green CI and a review.
- Protect `main` in the repository settings (no direct pushes, CI required).
- Never commit `.env.dev` or `.env.prod`. Only the `*.example` files are tracked.

## Running without Docker (faster edit loop)

Backend:

```powershell
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
$env:NEO4J_URI = "bolt://localhost:7687"; $env:OLLAMA_BASE_URL = "http://localhost:11434"
uvicorn app.main:app --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

## Quality checks

```powershell
cd backend;  ruff check .; ruff format --check .; mypy app; pytest -q
cd frontend; npm run lint; npm test; npm run build
```

`pytest` skips the Neo4j integration tests unless `TEST_NEO4J_URI` is set (see
`backend/tests/test_integration_neo4j.py`); CI runs them against a Neo4j service container.

CI (`.github/workflows/ci.yml`) runs the same checks on every push and pull request to `main` and
`develop`, and validates both Compose stacks.

## Repository layout

```
backend/            FastAPI app: core, health, and one folder per module
  app/deals/ documents/ copilot/ llm/ audit/ seed/ db/ common/   (day 1)
  app/orderbook/ investors/                                      (planned)
frontend/           Next.js (App Router, TypeScript)
scripts/            check-env.ps1 (Windows environment check)
docker-compose.yml  base stack; dev and prod overrides alongside
.github/workflows/  CI
```

Module rule for later scaling: modules never import each other's internals and each owns its own
data access, so any module can be split into a service later.

## How this project was built

It was built with AI assistance (Claude), working from a written scope and plan, and then reviewed,
run and understood by the author. The commit history and `docs/day-1-guide.md` show the decisions.
Anyone reading this repository should be told that plainly, and this section does so.

## Limits

This is a demo. A real bank would additionally need identity and entitlements (SSO), a security and
model-risk review, data governance, resilience and performance testing, and integration with the real
systems of record.
