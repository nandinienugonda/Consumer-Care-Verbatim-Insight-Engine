# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Summary

**CCVIE** — Consumer Care Verbatim Insight Engine. Detects emerging product issues from customer feedback through a five-layer architecture: Data Foundation (PostgreSQL + pgvector), Router (threshold-based entity rules), Retrieval and Generation (hybrid search + LLM synthesis), Attribution UI (Next.js), and Evaluation (regression gate).

## Architecture: Five Layers

| Layer | Path | Purpose |
|-------|------|---------|
| 1: Data Foundation | `backend/src/ccvie/data_foundation/` | Database, embeddings, ingestion |
| 2: Router | `backend/src/ccvie/router/` | Entity-based routing rules, LangGraph |
| 3: Retrieval and Generation | `backend/src/ccvie/retrieval_gen/` | Hybrid retrieval, LLM synthesis, FastAPI |
| 4: Attribution UI | `frontend/` | Insight feed and verbatim drill-down, Next.js |
| 5: Evaluation | `backend/src/ccvie/evaluation/` | Lead time, citation accuracy, regression gate |

## Three Core Rules

**Rule 1: Contracts live only in `backend/src/ccvie/contracts/`.** This is the single source of truth for all API data shapes. FastAPI route handlers use these Pydantic classes directly as request/response types. The frontend generates TypeScript types from the live OpenAPI schema via `npm run gen-types`, never by hand. CI verifies the generated file matches.

**Rule 2: Configuration lives only in `backend/src/ccvie/config.py`.** One `Settings` class (pydantic-settings) holds every configuration value. No file reads an environment variable directly except that one object. All env vars are listed in `.env.example`, grouped by layer.

**Rule 3: No file states a model name except `config.py` and `.env` files.** LLM model names (e.g., `claude-3-sonnet`, `gpt-4`) belong only in `config.py` and `.env*` files. This keeps model choices easy to change and prevents leaking them into code.

## Key File Locations

- **Architecture decisions**: `docs/project-architecture-proposal.md` is the canonical reference (detailed specification of the entire structure).
- **Golden set** (defines correct system behavior): `data/golden/`
  - `planted_issue_ground_truth.json` — ground truth for planted issues (used by eval tests)
  - `router_labeled_queries.json` — labeled query pairs and their correct paths
  - `eval_fixture.jsonl` — small fixed dataset for the CI gate
- **Generated data**: `data/generated/` is gitignored. Do not commit. Regenerate as needed.

## Common Development Commands

### Setup

```powershell
# Windows PowerShell initial setup
.\bootstrap.ps1

# Or install individual components
cd backend && py -m pip install -e . && cd ..
cd frontend && npm install && cd ..
```

### Database

```powershell
# Start PostgreSQL + pgvector container
docker compose up -d db

# Apply every pending file in db/migrations/ (idempotent, records schema_migrations)
cd backend && py -m ccvie.data_foundation.migrate && cd ..

# Load seed taxonomy
docker exec ccvie-db psql -U ccvie -d ccvie -f db/seed/seed_taxonomy.sql

# Generate schema snapshot after any migration
docker exec ccvie-db pg_dump -U ccvie -d ccvie --schema-only > db/schema.sql
```

### Frontend

```powershell
cd frontend

npm run dev           # development server (http://localhost:3000)
npm run type-check   # TypeScript check
npm run lint         # ESLint
npm run test         # Unit tests (Vitest)
npm run build        # Production build
npm run gen-types    # Regenerate types from backend OpenAPI
```

### Backend

```powershell
cd backend

# Start FastAPI with live reload (http://localhost:8000)
py -m uvicorn ccvie.api.app:app --reload --port 8000

# Unit and integration tests
py -m pytest tests/unit tests/integration

# Evaluation tests (CI gate)
py -m pytest tests/eval
```

## Project Structure

> **Note:** The `packages/` directory (`core`, `data-gen`, `eval`, `graph`, `retrieval`, `router`, `ui`, `vector`) contains TypeScript source and `dist/` output but is **not** listed in `pnpm-workspace.yaml` (which only includes `frontend`) and has no `package.json` files. It is not part of the active build — do not treat it as live architecture or wire new code into it without confirming with the user first.

```
backend/
├── src/ccvie/
│   ├── contracts/             ← API data shapes (Pydantic models) — SINGLE SOURCE OF TRUTH
│   ├── config.py              ← All configuration (Settings object) — ONLY ENV VAR READER
│   ├── data_foundation/       ← Database, embeddings, ingestion
│   ├── router/                ← Entity routing rules, LangGraph
│   ├── retrieval_gen/         ← Hybrid search, LLM synthesis, FastAPI
│   └── evaluation/            ← Regression gate, scoring, lead time
└── tests/

frontend/
├── src/
│   ├── app/                   ← Next.js pages (feed, drill-down)
│   ├── components/            ← UI components
│   ├── lib/
│   │   ├── types.generated.ts ← Generated from backend OpenAPI (do not edit by hand)
│   │   └── api-client.ts      ← Backend API client
│   └── mocks/                 ← Mock data for Day-1 UI development

db/
├── migrations/                ← Numbered SQL migration files
├── seed/                      ← Seed data (taxonomy)
└── schema.sql                 ← Generated, committed snapshot

data/
├── generators/                ← Scripts to generate synthetic data (committed)
├── golden/                    ← Ground truth for eval tests (committed)
└── generated/                 ← Gitignored bulk output (never commit)
```

## Code Style and Tools

**Frontend:**
- ESLint (no `console.log`, no unused vars)
- Prettier: 100-char line width, double quotes, trailing commas (es5), semicolons
- Radix UI + shadcn/ui components

**Backend:**
- FastAPI + Pydantic for API definitions
- Asyncpg for database access (connection pooling in `data_foundation/db.py`)
- Configuration via `config.py` (pydantic-settings)
- Pytest for testing

**Database:**
- PostgreSQL 16 with pgvector extension
- Migrations in plain SQL, applied in order
- Always regenerate `db/schema.sql` after migration changes

## Three Explicit Warnings

1. **Do not add a graph database.** The entity model is a shallow hierarchy (Product, Pack, Region, IssueType, Verbatim) that fits plain SQL tables. Neo4j is unnecessary.

2. **Do not expand the router into a multi-agent system.** Keep it a thin LangGraph over fixed threshold rules in `config.py`. Agentic loops add latency and unpredictability.

3. **Do not commit files under `data/generated/`.** This folder is gitignored on purpose. Bulk synthetic output can be regenerated at any time.

## Running the Full Stack

1. Copy `.env.example` to `.env` and fill in blanks (especially `LLM_MODEL_NAME`).
2. Run `.\bootstrap.ps1` to install dependencies.
3. Run `docker compose up -d db` to start the database.
4. Apply migrations and seed data (see Database commands above).
5. Start the backend: `cd backend && py -m uvicorn ccvie.api.app:app --reload --port 8000`
6. Start the frontend: `cd frontend && npm run dev`

The frontend currently uses mock data. It will switch to live API calls once backend routes are implemented.
