# AI_PROMPTS.md

This project was built with heavy AI assistance (Claude). Below is each prompt
used, what was generated correctly, what needed fixing, and how each piece was
verified — in the order the system was actually built.

---

## Prompt 1 – Architecture
> "I'm building a FastAPI + React + PostgreSQL system for seat allocation
> across ~5,000 employees, with projects, floors/zones/seats, and an AI query
> assistant. Propose a folder structure for the backend (routers, models,
> schemas, services) and frontend (feature-based folders), and explain the
> reasoning for separating the AI assistant logic from the route handlers."

**What AI generated correctly:** A clean split of `models.py` / `schemas.py`
/ `services.py` / `routers/`, and the reasoning for keeping `ai_assistant.py`
as its own module that calls into the same service functions the REST API
uses (so the assistant's answers can never drift from what the API reports).

**What AI generated incorrectly:** N/A — this stage is planning only.

**What I manually fixed:** N/A.

**How I verified:** Confirmed the resulting structure actually builds and
imports cleanly (`uvicorn app.main:app` starts without circular-import
errors).

---

## Prompt 2 – Database Design
> "Given these entities: employees, projects, seats, seat_allocations [schema
> pasted], write SQLAlchemy models with proper foreign keys, enum types for
> status fields, and a unique constraint ensuring a seat is unique per
> floor+zone+seat_number. Also write the Alembic migration."

**What AI generated correctly:** Enum columns for all four status fields,
the `UniqueConstraint("floor", "zone", "seat_number")` on `seats`, and
foreign keys with the right nullability (`employees.project_id` nullable for
unmapped new joiners).

**What AI generated incorrectly:** The first draft tried to enforce "one
active allocation per employee/seat" with a SQLite partial unique index,
which isn't portable to how the app also needs to run the same models
against Postgres without a dialect-specific migration branch.

**What I manually fixed:** Moved that rule into the application layer
(`services.py`), checked immediately before every insert/commit, so it works
identically on SQLite and Postgres with no per-dialect migration code.

**How I verified:** Ran `alembic revision --autogenerate` and `alembic
upgrade head` against a clean SQLite file, then inspected `sqlite_master` to
confirm all four tables and their indexes were created.

---

## Prompt 3 – Backend APIs
> "Write FastAPI routers for Employee CRUD and Project CRUD following REST
> conventions from this spec: [endpoint list]. Use Pydantic schemas for
> request/response validation, and return 409 Conflict for duplicate email."

**What AI generated correctly:** Full CRUD routers, 409 on duplicate email
and duplicate employee_code, 404 on missing IDs.

**What AI generated incorrectly:** Nothing structurally wrong, but the first
version returned raw ORM objects instead of a shaped `EmployeeOut` that
includes `project_name` and `current_seat` (derived fields the frontend
actually needs).

**What I manually fixed:** Added a `_to_out()` helper in `employees.py` that
joins in the project name and the live "current seat" lookup from
`seat_allocations`.

**How I verified:** `curl -s localhost:8000/employees?limit=2` and checked
the response includes `project_name` and `current_seat` correctly for both a
pending (unallocated) and an active (allocated) employee.

---

## Prompt 4 – Seat Allocation Logic
> "Write the seat allocation service function: given an employee_id and
> project_id, find an available seat prioritizing the same floor/zone as
> other active members of that project; if none available in that zone,
> fall back to any available seat and flag it as 'alternate zone'. Enforce:
> one active allocation per employee, one active allocation per seat.
> Include the release_seat function that marks the seat available again."

**What AI generated correctly:** The proximity search (find zones used by
active teammates, then look for a free seat in one of those zones first),
the fallback-to-any-available-seat path with `alternate_zone=True`, and both
rule checks (employee and seat) right before commit.

**What AI generated incorrectly:** Nothing behaviorally wrong; caught one
edge case worth calling out explicitly — re-checking the seat isn't taken
"right before commit" is what actually prevents a race where two requests
target the same seat, not just the earlier existence check.

**What I manually fixed:** Kept the re-check as written but added a test
(`test_alternate_zone_when_preferred_zone_full`) specifically to prove the
fallback path is reachable and correctly flagged.

**How I verified:** `pytest tests/test_seat_allocation.py -v` — 5/5 passing,
covering successful allocation, duplicate allocation rejection, release +
re-allocation of the same seat, alternate-zone fallback, and rejection of
allocating a reserved seat directly.

---

## Prompt 5 – AI Assistant
> "Build an intent-parsing function in Python that takes a natural language
> query like 'Where is employee Amit seated?' and extracts: intent
> (seat_lookup / project_lookup / availability_check / utilization_check) and
> entities (employee name/email, floor, zone, project name). Use simple
> keyword + regex matching, no external NLP library. Then write the handler
> that maps each intent to the correct existing service function and formats
> a natural-language response like: 'Amit is seated on Floor 2, Zone B, Bay
> 4, Seat B4-23, assigned to Project Talos.'"

**What AI generated correctly:** Keyword-based intent classification for all
5 required intents plus a 6th (`allocate_request`) since the brief's sample
queries include "Allocate a seat for a new employee joining today", and
regex extraction for email/floor/zone/project name.

**What AI generated incorrectly:** The name-extraction regex initially only
matched "employee <Name>" patterns, so "Where is my seat?" style
first-person queries (with an email instead of a name) fell through to "not
found" even when a valid email was present.

**What I manually fixed:** Added `_resolve_employee()` to try email first,
then name, and adjusted response phrasing to say "You are" vs "<Name> is"
depending on whether the query used a name or was first-person.

**How I verified:** Manually queried `/ai/query` against real seeded data:
`"Where is employee <real name> seated?"`, `"Where is my seat? My email is
<real email>"`, `"Show all available seats on Floor 3"`, and `"How many
seats are occupied for Project Indigo?"` — all four returned correct,
data-grounded answers (see Screenshots).

---

## Prompt 6 – Frontend
> "Build a React component using Tailwind for [employee search table /
> dashboard cards / seat allocation form]. Use React Query for data fetching
> against these endpoints: [endpoint list]. Keep components small and
> colocate query hooks with the feature folder."

**What AI generated correctly:** Working search/filter table, a dashboard
with stat cards + two Recharts bar charts (project utilization, floor
occupancy), and an allocate/release form wired to real mutations with
`onSuccess` cache invalidation.

**What AI generated incorrectly:** The first pass didn't invalidate the
dashboard queries after an allocate/release action, so the dashboard numbers
would go stale until a manual refresh.

**What I manually fixed:** Added explicit `queryClient.invalidateQueries()`
calls for `dashboard-summary`, `project-utilization`, and `floor-utilization`
inside both mutation `onSuccess` handlers in `SeatAllocation.jsx`.

**How I verified:** `npm run build` completes cleanly with no errors; ran
the dev server against the live backend and confirmed API calls resolve
(checked via `curl` against both `:5173` and `:8000` while both were
running).

---

## Prompt 7 – Testing
> "Write pytest tests for the seat allocation service covering: successful
> allocation, duplicate allocation attempt (should fail), releasing a seat
> and re-allocating it, and allocation when the preferred zone is full
> (should suggest alternate zone)."

**What AI generated correctly:** All four required cases, using an in-memory
SQLite fixture so tests don't touch the real dev database.

**What AI generated incorrectly:** Nothing needed fixing here.

**What I manually fixed:** Added one extra test
(`test_reserved_or_occupied_seat_cannot_be_directly_allocated`) beyond the
four asked for, since Business Rule 4 (reserved seats can't be allocated)
wasn't otherwise covered.

**How I verified:** `pytest -v` — all 5 tests pass.

---

## Prompt 8 – Debugging
> "Here's the error I'm getting: [traceback]. Here's the relevant code:
> [function]. Explain what's causing it before suggesting a fix."

**Real example hit during this build:** The first seed script assigned seat
statuses (available/reserved/occupied) independently from which employees
were active, using fixed counts (500 available / 100 reserved / rest
occupied) regardless of how many employees actually needed a seat. This
produced 5,000 "occupied" seats but only 4,940 active employees — 60 seats
marked occupied with no matching allocation row, which would have made the
dashboard's occupied-seat count inconsistent with the allocations table.

**Explanation before fixing:** The bug was a planning-order issue — seat
statuses were assigned before employee statuses were decided, so the two
counts couldn't be guaranteed to line up.

**What I manually fixed:** Reordered the script to decide pending vs. active
employees first, then size the "occupied" seat pool to exactly
`len(active_employees)`, with available/reserved seats computed from what's
left over (with a runtime check that the available count still clears the
500-seat minimum).

**How I verified:** Re-ran the seed script and printed counts — output
confirmed `occupied_seats == active_employees` exactly (4,940 both), with
560 available (above the 500 minimum) and 100 reserved.

**Second real example (release seat not working correctly):** Manually
testing the flow "employee leaves → HR deactivates them via `DELETE
/employees/{id}`" showed their seat stayed `occupied` forever with no way
to free it. Root cause: `deactivate_employee` only flipped
`employee.status` to `inactive` — it never called `release_seat`, so the
`SeatAllocation` row stayed `active` and the seat could never be
reallocated to anyone else, even though the employee no longer needed it.
Separately, `POST /seats/release` returned an `AllocationOut` without the
nested `seat` object (unlike `POST /seats/allocate`, which does include
it), so callers had no easy way to confirm which seat had just been freed.

**Explanation before fixing:** Both were omissions rather than logic
errors — `allocate_seat`/`release_seat` in `services.py` were already
correct in isolation (covered by the existing allocation/release tests);
the bug was that `deactivate_employee` never invoked the release path at
all, and the release *route* built its response differently from the
allocate route.

**What I manually fixed:**
- `deactivate_employee` now calls `release_seat(db, employee_id=...)`
  before marking the employee inactive, catching `AllocationError` for the
  (valid) case where the employee had no active seat to begin with.
- `POST /seats/release` now populates `seat` on the response the same way
  `POST /seats/allocate` already does.
- On the frontend, the "Release a Seat" form used to take a raw employee
  ID with no validation or feedback; it now reuses the same name/email/code
  search as the allocate form, previews the employee's current seat before
  the button is enabled, and shows the released seat in the success
  message. Added a "Currently Occupied Seats" panel with a one-click
  release button per seat as a second way to release without needing an ID
  at all.

**How I verified:** Added `test_release_by_seat_id_also_works`,
`test_release_with_no_active_allocation_raises`, and a
`TestDeactivationReleasesSeat` class to
`tests/test_seat_allocation.py`, plus a new `tests/test_employees_api.py`
using FastAPI's `TestClient` to exercise the real HTTP endpoints
end-to-end (`test_deactivating_employee_releases_their_seat`,
`test_deactivating_unseated_employee_still_succeeds`,
`test_release_response_includes_seat_details`). `pytest -v` passes for
all of the above.

---

## Prompt 9 – Deployment
> "Walk me through deploying a FastAPI app with a PostgreSQL database to
> Render, and a Vite React app to Vercel, including environment variable
> setup for the API base URL and database connection string."

**What AI generated correctly:** The `DATABASE_URL` / `CORS_ORIGINS` /
`VITE_API_BASE_URL` env var pattern, and confirmation that Swagger docs at
`/docs` satisfy the API-documentation submission requirement automatically.
Backend was deployed to Render using its native Python runtime (Build
Command: `pip install -r requirements.txt`, Start Command: `uvicorn
app.main:app --host 0.0.0.0 --port $PORT`) rather than the originally
suggested Docker route — no Dockerfile needed for this hosting choice.
Frontend deployed to Vercel with `VITE_API_BASE_URL` pointed at the Render
backend.

**What AI generated incorrectly / real issues hit during actual deployment:**

1. **`alembic upgrade head` failed with `psycopg2.errors.DuplicateObject:
   type "projectstatus" already exists`** the first time it ran against the
   fresh Render Postgres database. Root cause: `main.py` had
   `Base.metadata.create_all(bind=engine)` executing on every app import —
   completely separate from Alembic. The app (or the seed script's own
   `Base.metadata.create_all`) had already created the tables/enum types
   directly at some point before the migration ran, so Alembic's
   `alembic_version` table showed no migration history while the schema
   objects already existed, causing the conflict.

2. **The seed script appeared to hang indefinitely** against the deployed
   Postgres instance, despite running in ~3 seconds locally against SQLite.
   Root cause, found by adding a `print(..., flush=True)` after every major
   step: the bottleneck was `db.bulk_update_mappings()` for seat statuses,
   which issues one individual `UPDATE` statement per row via `executemany`
   — roughly 5,600 separate network round trips to Render's Oregon region.
   Separately, earlier `db.refresh()` calls after every insert (for 5,000
   employees and 5,600 seats) had the same one-round-trip-per-row problem.

3. **After deploying both services, the frontend failed every dashboard
   call with a CORS error** (`No 'Access-Control-Allow-Origin' header is
   present`). Root cause was two-fold: Render's environment variable change
   for `CORS_ORIGINS` required a manual redeploy to actually take effect
   (setting it in the dashboard alone didn't restart the running service),
   and the value needs an exact string match against the frontend's origin
   (no trailing slash, no surrounding quotes) since `main.py` does
   `os.getenv("CORS_ORIGINS", ...).split(",")` with no normalization.

**What I manually fixed:**
- Removed `Base.metadata.create_all(bind=engine)` from `main.py` entirely.
  Alembic is now the single source of schema truth — confirmed by the
  comment left in place explaining why, so this doesn't get re-added later.
- Rewrote `reset_db()` in `seed.py` to delete rows via `DELETE FROM` instead
  of `drop_all()`/`create_all()` (which was *also* bypassing Alembic and
  additionally dangerous to run against a live database), and added a
  `CONFIRM_SEED_RESET=yes` environment-variable guard so it refuses to run
  destructively against any non-SQLite `DATABASE_URL` without explicit
  confirmation.
- Rewrote the seat-status update step to use three `WHERE id IN (...)`
  bulk `UPDATE` statements (one per status: occupied/reserved/available)
  instead of one `UPDATE` per row, and replaced the per-row `db.refresh()`
  calls after bulk inserts with `db.bulk_save_objects()` followed by a
  single `SELECT ... ORDER BY id` per table to recover the newly assigned
  IDs — reducing seed time from an unbounded hang to a few seconds even
  over the network.
- Added `connect_timeout=10` to the Postgres connection args in
  `database.py`, so a genuine connection failure now surfaces as a clear
  error within 10 seconds instead of hanging indefinitely — this was added
  specifically so future connection issues are distinguishable from slow
  queries.
- Set `CORS_ORIGINS` on Render to the exact Vercel origin string and
  triggered a manual redeploy for it to take effect.

**How I verified:**
- Ran `alembic upgrade head` against the cleaned Render Postgres instance
  and confirmed the log showed `Context impl PostgresqlImpl` with no errors.
- Ran the rewritten seed script with step-by-step progress logging and
  confirmed it completed in seconds; queried the live database directly
  afterward to confirm exact counts: 5,000 employees, 5,600 seats, 4,940
  active allocations, matching every minimum in the brief.
- Hit the live backend directly:
  `curl https://seat-allocation-y2n8.onrender.com/dashboard/summary` —
  returned real, correct totals.
- Loaded the live frontend at
  `https://seat-allocation-flax.vercel.app` and confirmed the dashboard,
  employee search, seat allocation, and AI assistant all load real data
  from the deployed backend with no CORS errors after the redeploy.

---

## Prompt 10 – Refactoring
> "Review this seat allocation function for edge cases I might have missed,
> and suggest how to make it more readable without changing behavior."

**What AI generated correctly:** Flagged that `get_active_allocation_for_seat`
should be re-checked immediately before commit (race condition between the
initial zone search and the final write), which was already how the
function was structured — confirmed rather than changed.

**What AI generated incorrectly:** N/A.

**What I manually fixed:** N/A — used this pass to confirm the existing
design, not to change it.

**How I verified:** Re-ran the full test suite after this review pass to
confirm no behavior changed (`pytest -v`, 5/5 still passing).

---

## Bonus – Seed Data
> "Write a Python script using Faker to generate seed data: 5,000 employees,
> 5 floors, 10 zones, 5,500 seats, 10 projects, ensuring at least 500 seats
> stay 'available', 100 'reserved', and 50 employees have no active
> allocation (pending). Output via SQLAlchemy bulk operations."

**What AI generated correctly:** Faker-based employee/project/seat
generation matching every minimum in the brief (5,600 seats > 5,500 min, 60
pending > 50 min).

**What AI generated incorrectly:** See Prompt 8 above — the seat-status vs.
employee-status mismatch bug.

**What I manually fixed:** Same fix as documented in Prompt 8.

**How I verified:** `python -m app.seed` output:
```
Seeded: 11 projects, 5600 seats, 5000 employees, 4940 active allocations.
Seats -> available: 560, reserved: 100, occupied: 4940
Employees -> pending: 60, active: 4940
```