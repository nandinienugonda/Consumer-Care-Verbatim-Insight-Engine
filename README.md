# 🔍 CCVIE — Consumer Care Verbatim Insight Engine

**Early detection of emerging product issues from customer feedback.**

## Layout

```
backend/src/ccvie/     Python. Layers 1, 2, 3, and 5. Contracts live in contracts/.
frontend/              Next.js attribution UI (Layer 4).
```

| Layer | Path |
|---|---|
| Data foundation | `backend/src/ccvie/data_foundation/` (PostgreSQL + pgvector) |
| Router | `backend/src/ccvie/router/` |
| Retrieval and API | `backend/src/ccvie/retrieval_gen/` |
| Attribution UI | `frontend/` |
| Evaluation | `backend/src/ccvie/evaluation/` |

API shapes are the Pydantic models in `backend/src/ccvie/contracts/`. `npm run gen-types` writes `frontend/src/lib/types.generated.ts` from those models.

## Local Setup

### Prerequisites

- **Python 3.11+** (check: `py --version`)
- **Node.js 22+** (check: `npm --version`)
- **Docker Desktop** (check: `docker --version`)

### Step 1: Bootstrap (Install all dependencies)

**Windows PowerShell:**
```powershell
.\bootstrap.ps1
```

This installs:
- Backend Python dependencies
- Frontend Node dependencies
- Sets up `frontend/.env.local`

**macOS/Linux:**
```bash
make bootstrap
```

### Step 2: Start the Database

```powershell
docker compose up -d db
```

Verify it's running:
```powershell
docker ps
```

You should see `ccvie-db` container with PostgreSQL + pgvector.

### Step 3: Start the Frontend

```powershell
cd frontend
npm run dev
```

Open: **http://localhost:3000**

The UI is live with mock data. The frontend does not call the API yet.

---

## Full Stack Setup (After Backend Code Arrives)

When the backend developer adds code, follow these steps:

### Apply Database Migrations

```powershell
# Applies every pending file in db/migrations/ in order
cd backend
py -m ccvie.data_foundation.migrate
```

### Seed Data

```powershell
docker exec ccvie-db psql -U ccvie -d ccvie -f db/seed/seed_taxonomy.sql
```

### Generate Frontend Types from Backend OpenAPI

```powershell
npm run gen-types
```

This reads the backend OpenAPI schema and generates `frontend/src/lib/types.generated.ts`.

### Start the Backend API (Python)

```powershell
cd backend
py -m pip install -e ".[dev]"
py -m uvicorn ccvie.api.app:app --reload --port 8000
```

The API listens on http://localhost:8000. Interactive docs: http://localhost:8000/docs.
It needs `AUTH_DEV_MODE=true` and a 32+ character `AUTH_DEV_SECRET` in `.env` for local
development (see `.env.example`). Mint a bearer token with `py scripts/dev_token.py --help`.

Or run the whole stack in containers: `docker compose up -d --build api` (starts db, redis,
applies migrations, then the API).

---

## Frontend Development

Start dev server:
```powershell
cd frontend
npm run dev
```

Run checks:
```powershell
npm run test       # Unit tests
npm run type-check # TypeScript check
npm run lint       # ESLint
npm run build      # Production build
```

## Backend Development (Python)

Once backend code arrives, install and start:
```powershell
cd backend
py -m pip install -e .
py -m uvicorn ccvie.api.app:app --reload --port 8000
```

---

## Project Structure

- `backend/` — Python API and layers 1-3, 5
- `frontend/` — Next.js UI (layer 4)
- `db/` — Database migrations and seed data
- `docs/` — Architecture decisions and runbooks
- `.env` — Configuration (copy from `.env.example` and fill in values)

See `docs/project-architecture-proposal.md` for the full architecture and team setup.
