# Ethara Seat Allocation & Project Mapping System

**Live frontend:** https://seat-allocation-flax.vercel.app
**Live backend / API docs (Swagger):** https://seat-allocation-y2n8.onrender.com/docs
**GitHub repository:** https://github.com/Divyasoni2906/seat_allocation
**Sample login credentials:** not applicable — this system has no authentication layer; all endpoints are open, matching the brief's baseline requirement (auth was not listed as required).

A full-stack system for managing seat allocation and project mapping for
~5,000 employees, with search/filter, a live dashboard, and a natural-language
AI assistant for seat/project queries.

## Stack

| Layer | Choice |
|---|---|
| Backend | FastAPI (Python), REST + auto Swagger docs at `/docs` |
| Frontend | React (Vite) + Tailwind CSS, React Query for data fetching |
| Database | SQLite for local dev, PostgreSQL for deployment (single env var swap) |
| ORM | SQLAlchemy + Alembic migrations |
| AI Assistant | Deterministic rule-based intent parser (see `app/ai_assistant.py`) |
| Deployment | Docker Compose (Postgres + backend + frontend), or Render/Vercel |

## Architecture

```
┌─────────────┐      REST/JSON      ┌──────────────┐      SQLAlchemy      ┌────────────┐
│   React SPA │  ─────────────────► │   FastAPI    │  ──────────────────► │ PostgreSQL │
│  (Vite)     │  ◄───────────────── │   Backend    │  ◄────────────────── │  / SQLite  │
└─────────────┘                     └──────┬───────┘                     └────────────┘
                                            │
                                     ┌──────▼───────┐
                                     │ AI Query      │
                                     │ Layer:        │
                                     │ Intent parser │
                                     │ (ai_assistant.py)│
                                     └───────────────┘
```

The AI assistant lives in its own module (`app/ai_assistant.py`) that the
`/ai/query` route calls into, rather than being baked into the route handler.
It reuses the same `services.py` functions the REST API uses, so answers are
always consistent with real DB state.

## Database Schema

```
employees        id, employee_code (unique), name, email (unique), department,
                 role, joining_date, status (active/inactive/pending),
                 project_id (FK, nullable), created_at, updated_at

projects         id, name (unique), description, manager_name,
                 status (active/inactive), created_at

seats            id, floor, zone, bay, seat_number,
                 status (available/occupied/reserved/maintenance),
                 UNIQUE(floor, zone, seat_number)

seat_allocations id, employee_id (FK), seat_id (FK), project_id (FK),
                 allocation_status (active/released),
                 allocation_date, released_date, alternate_zone
```

Key decisions:
- The employee's "current seat" is **derived** from `seat_allocations` where
  `allocation_status='active'`, not stored directly on `employees`. This keeps
  full seat history and makes releases non-destructive.
- "One active allocation per employee/seat" is enforced in the application
  layer (`app/services.py`), checked immediately before every write.
- Indexes on `employees.email`, `seats.status`, `seat_allocations.allocation_status`
  for the dashboard's frequent filtered counts.

## Business Rules Implemented

1. One employee can have only one active seat allocation.
2. One seat can have only one active allocation.
3. Released seats become available again.
4. Reserved/maintenance seats can't be allocated directly.
5. New joiners are prioritized for seats in the same floor/zone as active
   teammates on their project; if none is free, the system falls back to any
   available seat and flags the allocation as `alternate_zone: true`.
6. Duplicate employee email is rejected (409).
7. Duplicate seat number on the same floor/zone is rejected (409).
8. Dashboard numbers are computed live from current DB state on every request.

## API Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/employees` | Create employee |
| GET | `/employees?search=&department=&status=&project_id=` | Search/filter employees |
| GET | `/employees/{id}` | Get employee details |
| PUT | `/employees/{id}` | Update employee |
| DELETE | `/employees/{id}` | Deactivate employee |
| POST | `/projects` | Create project |
| GET | `/projects` | List projects |
| GET | `/projects/{id}/employees` | List employees in a project |
| POST | `/seats` | Create seat |
| GET | `/seats?floor=&zone=&status=` | List seats |
| GET | `/seats/available?floor=&zone=` | List available seats |
| POST | `/seats/allocate` | Allocate seat `{employee_id, project_id?}` |
| POST | `/seats/release` | Release seat `{employee_id}` or `{seat_id}` |
| GET | `/dashboard/summary` | Totals: employees, seats by status, pending joiners |
| GET | `/dashboard/project-utilization` | Seats occupied per project |
| GET | `/dashboard/floor-utilization` | Seat status breakdown per floor |
| POST | `/ai/query` | Natural-language query `{query: "..."}` |

Full interactive docs (Swagger) are served automatically at **`/docs`**.

## Local Setup

### Backend
```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # defaults to SQLite, no edits needed for local dev
alembic upgrade head                # create tables via migrations
python -m app.seed                  # generate seed data (5,000 employees, 5,600 seats, etc.)
uvicorn app.main:app --reload --port 8000
```
API is now live at `http://localhost:8000`, docs at `http://localhost:8000/docs`.

### Frontend
```bash
cd frontend
npm install
cp .env.example .env                # VITE_API_BASE_URL=http://localhost:8000
npm run dev
```
App is now live at `http://localhost:5173`.

### With Docker Compose (Postgres + backend + frontend)
```bash
docker compose up --build
# then, one-time, apply migrations + seed against the running Postgres container:
docker compose exec backend alembic upgrade head
docker compose exec backend python -m app.seed
```

### Tests
```bash
cd backend
pytest -v
```
Covers: successful allocation, duplicate allocation rejection, release +
re-allocation, and fallback-to-alternate-zone when the preferred zone is full.

## Switching to PostgreSQL for Deployment

Set `DATABASE_URL` to a Postgres connection string, e.g.:
```
DATABASE_URL=postgresql://user:pass@host:5432/dbname
```
No code changes needed — SQLAlchemy handles the dialect swap. Run
`alembic upgrade head` once against the new URL, then seed if desired.

## Deployment Notes

This was actually deployed (not just planned) as follows:

**Backend → Render (native Python runtime, not Docker):**
- New Web Service, root directory `backend/`
- Build Command: `pip install -r requirements.txt`
- Start Command: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
  — the `alembic upgrade head &&` prefix is required, not optional: this app
  creates its schema exclusively through Alembic (see the `main.py` note
  above), so without running migrations first on every deploy, a fresh
  Postgres instance would have no tables and every request would 500.
- Environment variables: `DATABASE_URL` (Render's Postgres internal
  connection string) and `CORS_ORIGINS` set to the exact Vercel URL,
  `https://seat-allocation-flax.vercel.app` — no trailing slash, no quotes
  around the value.

**Frontend → Vercel:**
- Import repo, root directory `frontend/`
- Environment variable `VITE_API_BASE_URL` set to
  `https://seat-allocation-y2n8.onrender.com`

**Real issues hit during this deployment (see `AI_PROMPTS.md` Prompt 9 for
full detail):**
1. `alembic upgrade head` failed with `DuplicateObject: type "projectstatus"
   already exists` the first time it ran against the fresh Render Postgres
   instance. Root cause: `main.py` had `Base.metadata.create_all(bind=engine)`
   running on every app boot, completely bypassing Alembic — if the app ever
   started against that database even once before migrations ran, it created
   the schema directly and left Alembic's own migration history out of sync.
   Fixed by removing that line entirely; Alembic is now the only thing that
   creates schema, ever.
2. The seed script hung for several minutes against the deployed Postgres
   instance (it was instant locally against SQLite). Root cause: it was
   issuing one individual network round trip per row — thousands of them —
   instead of batched statements. Fixed by switching to `bulk_save_objects`
   for inserts and three `WHERE id IN (...)` statements for the seat-status
   update instead of one `UPDATE` per row.
3. After both services were live, the frontend failed with CORS errors on
   every dashboard call. Root cause: `CORS_ORIGINS` on Render needed a
   redeploy to actually take effect after being set, and required an exact
   string match (no trailing slash, no surrounding quotes) against the
   Vercel origin.

Swagger docs are automatically available at `/docs` on the deployed
backend — that satisfies the "API documentation link" submission
requirement with no extra work: https://seat-allocation-y2n8.onrender.com/docs

## AI Assistant Design Note

The assistant is a **deterministic rule-based intent parser**, not an LLM
call — see `app/ai_assistant.py`. Reasoning:
- The query space is small and fully known in advance (the 5 intent types
  the brief specifies).
- Answers must always match real, current seat/employee data — determinism
  matters more than open-ended flexibility here.
- Zero API cost, no latency, no key management, and it works offline in a
  demo.
- An LLM fallback could be bolted on later purely to normalize free-form
  phrasing into one of the existing intents, then route to the same
  deterministic functions — the core logic wouldn't change.

## Submission Checklist

| Requirement | Status / Location |
|---|---|
| GitHub repository | https://github.com/Divyasoni2906/seat_allocation |
| Live frontend URL | https://seat-allocation-flax.vercel.app |
| Live backend URL | https://seat-allocation-y2n8.onrender.com |
| README.md | This file |
| AI_PROMPTS.md | `AI_PROMPTS.md` in repo root |
| Database schema | `backend/alembic/versions/` (migration files), also documented above |
| Sample seed data | `backend/app/seed.py` — run via `python -m app.seed` |
| Sample login credentials | Not applicable — no authentication layer |
| Screenshots | root directory — see below |
| API documentation | https://seat-allocation-y2n8.onrender.com/docs (Swagger, auto-generated) |
| Debugging notes | `AI_PROMPTS.md`, Prompt 8 and Prompt 9 sections |
| Deployment notes | This file, "Deployment Notes" section above |

### Screenshots

![Dashboard](dashboard.png)
![Employee Search](employees.png)
![Seat Allocation](seat_allocation.png)
![AI Assistant](ai_assistant.png)
<img width="1361" height="626" alt="image" src="https://github.com/user-attachments/assets/66733b4b-3708-4f52-9c62-a1fac50a4a64" />

![Project dashboard](projects.png)

Capture each directly from the live frontend:
1. **`dashboard.png`** — the Dashboard tab, showing the stat cards and both charts with real data
2. **`employees.png`** — the Employees tab with a search term entered and results showing
3. **`seat_allocation.png`** — the Seat Allocation tab, ideally right after a successful allocation (showing the success message)
4. **`ai_assistant.png`** — the AI Assistant tab with at least one question asked and answered, e.g. "Where is employee &lt;name&gt; seated?"
5. **`projects.png`** - shows all the projects and employees grouped together through projects.


```
ethara/
├── backend/
│   ├── app/
│   │   ├── main.py            FastAPI app + CORS + router wiring
│   │   ├── database.py        SQLAlchemy engine/session (SQLite/Postgres)
│   │   ├── models.py          ORM models
│   │   ├── schemas.py         Pydantic request/response schemas
│   │   ├── services.py        Seat allocation business logic
│   │   ├── ai_assistant.py    Rule-based NL query parser
│   │   ├── seed.py            Faker-based seed data generator
│   │   └── routers/           employees.py, projects.py, seats.py, dashboard.py, ai.py
│   ├── alembic/                Migration history
│   ├── tests/test_seat_allocation.py
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx            Nav + routes
│   │   ├── api.js              API client
│   │   └── pages/              Dashboard, EmployeeSearch, SeatAllocation, Projects, AIAssistant
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── AI_PROMPTS.md
└── README.md
```
