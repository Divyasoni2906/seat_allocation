# Ethara Seat Allocation & Project Mapping System

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

- **Backend → Render**: new Web Service from this repo (`backend/` as root),
  add a PostgreSQL instance, set `DATABASE_URL` to its connection string and
  `CORS_ORIGINS` to your deployed frontend URL. Run `alembic upgrade head`
  once against the remote DB (via Render's shell or locally pointed at the
  remote URL).
- **Frontend → Vercel**: import repo with `frontend/` as root, set
  `VITE_API_BASE_URL` to the Render backend URL.
- Swagger docs are automatically available at `/docs` on the deployed
  backend — that satisfies the "API documentation link" requirement with no
  extra work.

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

## Repository Structure

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
