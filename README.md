# Clinic Booking API

A Django REST Framework API for booking, cancelling and rescheduling 30-minute clinic appointments, with
per-doctor weekly working hours, slot availability, and database-level protection against double booking.

**Live API (Render):** https://clinic-booking-api-80cr.onrender.com/api/docs/ (Swagger UI)
· Schema: https://clinic-booking-api-80cr.onrender.com/api/schema/
· Example: https://clinic-booking-api-80cr.onrender.com/api/doctors/

> Hosted on Render's free tier: the service sleeps when idle, so the first request can take ~30–60 s.

> **Security limitation — read first.** Authentication and authorisation are intentionally **not
> implemented** in this assessment build. Every endpoint is open, and knowing a patient ID is enough to
> read that patient's appointments. Numeric IDs are guessable and are **not** an access-control
> mechanism. Do not deploy this with real patient or medical data until authentication (e.g. token/JWT
> auth) and per-patient object permissions are added.

## System design

### The problem, restated

> *A small clinic with 5 doctors. Each doctor has set working hours and works in 30-minute slots. A patient
> sees which slots are free for a doctor on a given day, picks one and books it. Once booked, the slot must
> not be available to anyone else. Patients can cancel. Start small, but be able to grow.*

From the brief, the system has to:

| # | Requirement from the brief | What it means for the design |
|---|---|---|
| R1 | Doctors have set working hours | Store a weekly schedule per doctor, separate from bookings |
| R2 | 30-minute slots | Fixed slot length and a fixed time grid (:00 / :30) |
| R3 | See free slots for a doctor on a day | Work out availability from schedule minus bookings |
| R4 | Pick a slot and book it | Validate the slot, then create the booking atomically |
| R5 | A booked slot must not be available to others | Guarantee no double booking, **even with concurrent requests** |
| R6 | Patients can cancel | Cancellation releases the slot but keeps the history |
| R7 | Start small, grow later | Simple monolith now, with clear seams for scaling later |

Things I assumed where the brief says nothing (kept explicit so they're easy to change):

- One clinic, one timezone (`Africa/Nairobi`). Working hours are local wall-clock times.
- A doctor may have several working blocks a day (e.g. a lunch break).
- Bookings must be made at least 1 hour in advance and never in the past.
- A patient can't hold two appointments at the same time, even with different doctors.
- Rescheduling is a convenience: it's an atomic "cancel + rebook" that keeps the same appointment record.

### Components

```
                ┌────────────────────────────────────────────────────────────┐
  HTTP client ─▶│  Django + DRF  (single deployable service)                 │
  (web / app)   │                                                            │
                │  URLs ─▶ Views (thin) ─▶ Serializers (input shape/types)   │
                │                 │                                          │
                │                 ▼                                          │
                │        appointments/services.py   ◀── business rules,      │
                │                 │                     transactions, locks  │
                │                 ▼                                          │
                │        Models (Doctor, WorkingHour, Patient, Appointment)  │
                └─────────────────┬──────────────────────────────────────────┘
                                  ▼
                     PostgreSQL (prod) / SQLite (local)
                     + partial unique indexes = final guard against double booking
```

| Component | Responsibility |
|---|---|
| `doctors` app | Doctors and their weekly working hours; the availability endpoint |
| `appointments` app | Patients and appointments; booking, cancelling and rescheduling endpoints |
| `appointments/services.py` | **The only place business rules live.** Views call it; tests target it via the API |
| Serializers | Input shape/type validation (e.g. "is this a datetime?") and output formatting, **not** business rules |
| Database constraints | Last line of defence: holds even if application code has a bug or a race slips through |
| drf-spectacular | OpenAPI schema + Swagger UI, so the API contract is self-documenting |

### Models identified

- **Doctor**: who can be booked (`name`, `specialization`, `is_active`).
- **DoctorWorkingHour**: the recurring weekly template: `(doctor, weekday, start_time, end_time)`. Several rows per day are allowed.
- **Patient**: who books (`name`, unique `email`). One patient → many appointments.
- **Appointment**: the booking itself: `doctor`, `patient`, `starts_at`, `ends_at`, `status` (`booked`/`cancelled`), `cancellation_reason`, timestamps.

A **Slot** is deliberately *not* a table (see decision 1). Full field details are in [Data models](#data-models).

### Key decisions

1. **Slots are computed, not stored.** Availability = the doctor's working blocks for that weekday, cut into
   30-minute steps, minus active appointments, minus anything in the past or within the 1-hour notice window.
   This keeps one source of truth (schedule + bookings). Changing a doctor's hours takes effect at once, with no
   batch job to pre-generate slots and nothing to keep in sync.

2. **No double booking is enforced by the database, not just the code (R5).** A *partial unique index* on
   `(doctor, starts_at) WHERE status = 'booked'` means only one active appointment per doctor per start time.
   Slots are fixed-length and grid-aligned, so "same start" is exactly "overlap", and a plain unique index is
   enough (no range/exclusion constraint needed). Cancelled rows are outside the index, so cancelling frees
   the slot automatically. A matching index on `(patient, starts_at)` stops a patient double-booking themselves.

3. **Concurrency: lock, then check, then let the constraint decide.** Booking runs in `transaction.atomic()`
   and locks the doctor row (`SELECT … FOR UPDATE`), so two simultaneous requests for the same doctor run one
   after the other on PostgreSQL. If anything still races, the unique index rejects the second insert and the
   API returns **409 Conflict**, never a double booking and never a 500.

4. **Cancellation is a status change, not a delete (R6).** Records keep `status=cancelled` and a required
   reason. This keeps an audit trail, supports reporting (no-show/cancellation rates) and makes "slot
   released" fall out of decision 2 for free.

5. **Business rules live in one service module.** Views stay thin. That makes the rules easy to read and
   test, and lets other entry points (admin actions, a future background job or message consumer) reuse
   them.

6. **The server owns time.** Clients send only `starts_at`; the server computes `ends_at` and validates the
   grid. All datetimes are timezone-aware (stored in UTC, presented in `Africa/Nairobi`).

7. **Meaningful HTTP semantics.** 400 = your request breaks a rule (misaligned, outside hours, too soon);
   409 = valid request but conflicts with current state (slot taken, already cancelled); 404 = unknown ID.
   Every business error carries a stable machine-readable `code` for clients.

8. **Integer IDs.** Simple and fast for a small system. (See trade-offs: they're guessable.)

### Trade-offs considered

| Decision | Alternative considered | Why I chose this (and the cost) |
|---|---|---|
| Computed slots | Pre-generated `Slot` rows per doctor/day | No sync job and no stale data. **Cost:** availability is computed per request, which is trivial at 5 doctors × ~18 slots/day. A `Slot` table would make sense if slots needed their own state (e.g. "held" during checkout). |
| Unique index on start time | PostgreSQL `ExclusionConstraint` on a `tstzrange` | Works on both SQLite and Postgres, and is simple. **Cost:** relies on fixed 30-min, grid-aligned slots. Variable-length appointments would need the exclusion constraint (Postgres-only). |
| Pessimistic lock on doctor row | Optimistic (just insert, catch `IntegrityError`) or serialisable isolation | Clear errors and predictable behaviour; the lock is held for milliseconds. **Cost:** bookings for the *same* doctor are serialised. Fine at clinic scale; the unique index alone would still be correct without the lock. |
| Soft-cancel (status) | Delete the row | Keeps history and an audit trail. **Cost:** queries must filter on `status`; covered by an index. |
| Weekly working-hours template | Calendar of explicit dates | Matches "set working hours", easy to seed and edit. **Cost:** no holidays/leave or one-off overrides yet (a natural next model: `DoctorTimeOff`). |
| Single timezone | Per-doctor/per-clinic timezone | One clinic, so one zone avoids confusion. **Cost:** a multi-site expansion needs a `Clinic` model with its own timezone. |
| Monolith with two apps | Separate services | Small team, small scope: one deployable unit, one database, ACID transactions across booking rules. **Cost:** scaling is vertical/horizontal replicas of the same app, which is plenty for now. |
| No auth (assessment scope) | Token/JWT + per-patient permissions | Time-boxed. **Cost:** unsuitable for real patient data; integer IDs are guessable. This is the first thing to add (see top-of-page warning). |
| Sync request/response only | Async jobs (email/SMS confirmations) | Nothing in the brief needs it yet. A task queue (Celery/RQ) slots in later at the service layer. |

### How this grows

Ordered roughly by likely need:

1. **Authentication & authorisation**: patient accounts, staff/admin roles, object-level permissions.
2. **Schedule exceptions**: `DoctorTimeOff` / holidays subtracted during availability calculation.
3. **Notifications**: confirmation/reminder emails or SMS through a background queue, triggered from the service layer.
4. **Multiple clinics/locations**: a `Clinic` model owning doctors and a timezone.
5. **Variable appointment types/lengths**: an `AppointmentType` with duration, plus a PostgreSQL exclusion constraint on time ranges.
6. **Read scaling**: the API is stateless, so add more web instances behind the load balancer; cache availability per doctor/day and invalidate on booking/cancel; use Postgres read replicas if needed.
7. **Pagination & filtering** on list endpoints, and **rate limiting** on booking to deter abuse.

## Tech stack

- Python 3.14, Django 6.1, Django REST Framework 3.18
- drf-spectacular (OpenAPI 3 + Swagger UI)
- django-environ for configuration
- SQLite locally, PostgreSQL in deployment (via `DATABASE_URL`)
- WhiteNoise for static files, Gunicorn as the WSGI server
- GitHub Actions CI, Render Blueprint for deployment

## Code layout

```
config/                 project settings, root URLs, WSGI
doctors/
  models.py             Doctor, DoctorWorkingHour
  serializers.py        doctor + availability serializers
  views.py              doctor list, availability endpoint
  management/commands/seed_clinic.py
appointments/
  models.py             Patient, Appointment (+ DB constraints)
  services.py           ALL booking business rules (book / cancel / reschedule / availability)
  exceptions.py         BookingError (400), SlotUnavailable (409), InvalidAppointmentState (409)
  serializers.py        request/response serializers (input shape validation only)
  views.py              thin HTTP layer: validate input -> call service -> serialise output
```

Request flow: **URL → view → input serializer (shape/type validation) → `services.py` (business rules,
transaction, locking) → model/DB constraints → output serializer**. Business rules live only in
`appointments/services.py`, so they are easy to test and are never duplicated across views.

IDs are auto-incrementing integers (`BigAutoField`) throughout.

## Data models

| Model | Fields | Notes |
|---|---|---|
| `Doctor` | `name`, `specialization`, `is_active` | Inactive doctors cannot be booked. |
| `DoctorWorkingHour` | `doctor` (FK), `weekday` (0=Mon … 6=Sun), `start_time`, `end_time` | Several blocks per day allowed (e.g. a lunch break). Check constraint `start_time < end_time`; unique per `(doctor, weekday, start_time)`. Times are clinic-local. |
| `Patient` | `name`, `email` (unique), `created_at` | One patient → many appointments (`patient.appointments`). |
| `Appointment` | `doctor` (FK), `patient` (FK), `starts_at`, `ends_at`, `status` (`booked`/`cancelled`), `cancellation_reason`, `created_at`, `updated_at` | Cancelled records are kept. FKs use `PROTECT` so history is never cascade-deleted. |

Database constraints on `Appointment`:

- `unique_active_doctor_slot`: partial unique index on `(doctor, starts_at) WHERE status = 'booked'`.
- `unique_active_patient_slot`: partial unique index on `(patient, starts_at) WHERE status = 'booked'`.
- `appointment_ends_after_start`: check constraint `ends_at > starts_at`.

Because every appointment is exactly 30 minutes and starts on a :00/:30 boundary, "same start time" is
equivalent to "overlapping", so the partial unique index enforces non-overlap at the database level on both
SQLite and PostgreSQL. Cancelled rows are excluded from the index, so a cancelled slot can be rebooked.

## Business rules

All enforced in `appointments/services.py`:

1. Appointments last exactly 30 minutes (`ends_at` is computed by the server; clients send only `starts_at`).
2. `starts_at` must be on a 30-minute boundary in clinic time (`09:00`, `09:30`, …), with no seconds.
3. The doctor must be active, and the whole slot must fall inside one of the doctor's working-hour blocks for that weekday.
4. Past slots are rejected (`past_slot`).
5. Slots less than 1 hour from now are rejected (`insufficient_notice`), which covers the bonus rule.
6. A slot that overlaps another active appointment for the same doctor, or for the same patient, is rejected with **409**.
7. Cancellation needs a non-blank reason. It keeps the record, sets `status=cancelled`, and frees the slot.
8. Cancelling an already-cancelled appointment returns **409** (`already_cancelled`).
9. Rescheduling a cancelled appointment returns **409** (`cancelled_appointment`).
10. Rescheduling is atomic: the new slot goes through every rule above (excluding the appointment itself), and if anything fails the transaction rolls back and the original slot is unchanged.
11. Timezone: `USE_TZ=True`, `TIME_ZONE=Africa/Nairobi`. Datetimes without an offset are treated as Nairobi time; responses are returned with `+03:00`.

### Concurrency

- Each write runs inside `transaction.atomic()`.
- Booking takes `SELECT … FOR UPDATE` on the doctor row, so on PostgreSQL concurrent bookings for the same doctor run one at a time and the overlap check cannot be raced. Rescheduling locks the appointment row and then the doctor row. Cancelling locks the appointment row.
- The partial unique indexes are the final guarantee. If two transactions still race (e.g. the same patient booking two doctors at once), the second insert fails with `IntegrityError`, which is returned as **409** `slot_unavailable`.
- SQLite ignores `FOR UPDATE` but serialises writers with a database-level lock; the unique indexes still apply.

### Error format & status codes

Business-rule errors return `{"detail": "...", "code": "..."}`. Serializer errors use DRF's standard
field → messages format.

| Status | When |
|---|---|
| 200 / 201 | Success |
| 400 | Invalid input, misaligned/past/too-soon slot, outside working hours, inactive doctor, missing reason |
| 404 | Unknown doctor / appointment / patient in the URL |
| 409 | Slot already taken, already cancelled, rescheduling a cancelled appointment |

## API

Interactive docs: **`/api/docs/`** (Swagger UI) · raw schema: **`/api/schema/`**

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/doctors/` | List doctors with weekly working hours (helper) |
| GET | `/api/doctors/<id>/availability/?date=YYYY-MM-DD` | Available 30-min slots |
| POST | `/api/patients/` | Register a patient (helper) |
| POST | `/api/appointments/` | Book an appointment |
| PATCH | `/api/appointments/<id>/cancel/` | Cancel (reason required) |
| PATCH | `/api/appointments/<id>/reschedule/` | Reschedule to a new slot |
| GET | `/api/patients/<id>/appointments/` | Upcoming active appointments, ordered by `starts_at` |

### Examples

```bash
# Availability
curl "http://127.0.0.1:8000/api/doctors/1/availability/?date=2026-10-23"
```
```json
{"doctor": 1, "date": "2026-10-23", "timezone": "Africa/Nairobi", "slot_minutes": 30,
 "slots": [{"starts_at": "2026-10-23T08:00:00+03:00", "ends_at": "2026-10-23T08:30:00+03:00"}, "..."]}
```

```bash
# Book
curl -X POST http://127.0.0.1:8000/api/appointments/ -H "Content-Type: application/json" \
  -d '{"doctor": 1, "patient": 1, "starts_at": "2026-10-23T09:00:00+03:00"}'
```
```json
{"id": 1, "doctor": 1, "doctor_name": "Dr. Amina Odhiambo", "patient": 1, "patient_name": "Demo Patient One",
 "starts_at": "2026-10-23T09:00:00+03:00", "ends_at": "2026-10-23T09:30:00+03:00", "status": "booked",
 "cancellation_reason": "", "created_at": "...", "updated_at": "..."}
```

```bash
# Same slot again -> 409
{"detail": "This slot is already booked for the doctor.", "code": "slot_unavailable"}

# Reschedule
curl -X PATCH http://127.0.0.1:8000/api/appointments/1/reschedule/ -H "Content-Type: application/json" \
  -d '{"starts_at": "2026-10-23T09:30:00+03:00"}'

# Cancel
curl -X PATCH http://127.0.0.1:8000/api/appointments/1/cancel/ -H "Content-Type: application/json" \
  -d '{"cancellation_reason": "Patient is travelling"}'

# Upcoming appointments for a patient
curl http://127.0.0.1:8000/api/patients/1/appointments/

# Register a patient
curl -X POST http://127.0.0.1:8000/api/patients/ -H "Content-Type: application/json" \
  -d '{"name": "Jane Doe", "email": "jane@example.com"}'
```

## Local setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # then edit DJANGO_SECRET_KEY; leave DATABASE_URL empty for SQLite
python manage.py migrate
python manage.py seed_clinic      # 5 doctors + weekly hours + 2 demo patients (idempotent)
python manage.py runserver
```

Open http://127.0.0.1:8000/api/docs/.

### Configuration (environment variables)

| Variable | Default | Purpose |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev-only key **when** `DJANGO_DEBUG=True`; required otherwise | Django secret key |
| `DJANGO_DEBUG` | `False` | Debug mode |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated hosts (`RENDER_EXTERNAL_HOSTNAME` is added automatically) |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Needed for the admin behind HTTPS on custom domains |
| `DATABASE_URL` | unset → SQLite `db.sqlite3` | e.g. `postgres://user:pass@host:5432/db` |
| `TIME_ZONE` | `Africa/Nairobi` | Clinic timezone |

### Migrations

```bash
python manage.py makemigrations          # after model changes
python manage.py migrate
python manage.py makemigrations --check --dry-run   # CI guard: fails if migrations are missing
```

### Tests

```bash
python manage.py test
```

27 tests cover: successful booking, duplicate booking (409), patient double booking, outside working
hours, days with no hours, misaligned slots, past appointments, the 1-hour notice rule, inactive doctors,
the DB unique constraint itself, cancellation, blank reason, repeated cancellation, released slots
(cancel → slot reappears and can be rebooked), successful rescheduling, failed rescheduling (occupied and
invalid slots, original preserved), rescheduling a cancelled appointment, the patient upcoming list
(ordering, excludes past/cancelled), availability, and the OpenAPI schema/Swagger page.

## CI/CD

### Summary

| | |
|---|---|
| **Public URL** | https://clinic-booking-api-80cr.onrender.com/api/docs/ |
| **Deploy branch** | `main` (only `main` deploys; other branches and PRs are tested but never deployed) |
| **How it deploys** | A merge or push to `main` triggers GitHub Actions CI. Render watches `main` and, with `autoDeployTrigger: checksPass`, starts a deploy **only after the CI checks for that commit pass**. A failing build never reaches production. |

```
feature branch ──PR──▶ CI runs (tests on SQLite + PostgreSQL)  ──review──▶ merge to main
                                                                              │
                         CI runs again on main ◀──────────────────────────────┘
                                │ all checks green
                                ▼
                 Render auto-deploy: pip install → collectstatic → migrate → seed → gunicorn
```

### What the pipeline does

**CI: GitHub Actions** (`.github/workflows/ci.yml`), triggered by **pushes to `main`** and **pull requests
targeting `main`**. It runs the same steps twice in parallel, once on **SQLite** and once on **PostgreSQL 16**
(a service container), so the partial unique indexes and row locking are exercised on the production database
engine:

1. Check out the code and install Python (version from `.python-version`) and the pinned `requirements.txt`.
2. `manage.py check --deploy --fail-level ERROR`: production-settings sanity checks.
3. `makemigrations --check --dry-run`: fails if a model change has no migration.
4. `spectacular --validate --fail-on-warn`: the OpenAPI schema must be valid.
5. `manage.py test`: the full test suite (27 tests).

**CD: Render** (`render.yaml` Blueprint), triggered by a passing commit on `main`:

1. **Build:** `pip install -r requirements.txt` and `collectstatic` (static files served by WhiteNoise).
2. **Start:** `migrate` (applies new migrations against the managed PostgreSQL), `seed_clinic` (idempotent
   demo data), then `gunicorn config.wsgi:application`.
3. **Health check:** Render polls `/api/doctors/` and switches traffic to the new version only once it
   responds, so a broken start keeps the previous version live.

Secrets are not in the repository: `DJANGO_SECRET_KEY` is generated by Render and `DATABASE_URL` is injected
from the Render PostgreSQL instance.

## Deployment (Render)

`render.yaml` is a Render Blueprint that provisions:

- a free PostgreSQL database (`clinic-booking-db`), and
- a Python web service that builds with `pip install` + `collectstatic`, then on start runs `migrate`,
  `seed_clinic` (idempotent) and `gunicorn config.wsgi:application`.

`DJANGO_SECRET_KEY` is generated by Render and `DATABASE_URL` is wired from the database. No secrets are in
the repository.

### Connecting GitHub to Render (auto-deploy on merge to `main`)

1. Push this repository to GitHub with `main` as the default branch.
2. In GitHub → *Settings → Branches*, add a branch protection rule for `main` that requires the **CI**
   checks to pass before merging (recommended).
3. In the Render dashboard: **New → Blueprint**, connect your GitHub account, and select this repository.
   Render reads `render.yaml` and shows the database and web service it will create. Click **Apply**.
4. Render watches the `main` branch. With `autoDeployTrigger: checksPass` it deploys after each push/merge to
   `main` **once GitHub checks have passed**. Change it to `commit` to deploy on every push without waiting.
5. After the first deploy, open `https://<service-name>.onrender.com/api/docs/`.

Notes: free Render services sleep when idle, so the first request after a while is slow. Render picks up the
Python version from `.python-version` (`3.14`). If your Render account does not support that version yet, set
a `PYTHON_VERSION` env var to a supported 3.12+ release (Django 6.1 needs Python 3.12 or newer).

> Deployment status: live at https://clinic-booking-api-80cr.onrender.com/api/docs/ (Swagger UI, schema
> and `/api/doctors/` verified responding with seeded data).

## Known limitations / next steps

- **No authentication or authorisation** (see the warning at the top). Next step: DRF token/JWT auth, staff vs patient roles, and object-level permissions so a patient can see only their own appointments.
- Appointments that have already happened can still be cancelled or rescheduled from their past slot. A real system would add `completed`/`no_show` statuses.
- No pagination on the patient list. Fine for the expected volume; add `PageNumberPagination` if needed.
- On PostgreSQL, an `ExclusionConstraint` on a `tstzrange` would let appointments have variable lengths. That isn't needed while every slot is a fixed 30 minutes on a grid.
- Doctor working hours are managed through the Django admin (`/admin/`), not through the API.

## AI reflection

> **TODO (author):** paste the four reflection questions from the assessment brief here and answer them in
> your own words.
>
> For reference, the facts behind your answers: the implementation was generated with Claude Code (an AI
> coding assistant) from a detailed prompt. The author then ran and reviewed `python manage.py test`, the
> migrations, the seed command and a manual curl smoke test, and checked the business rules, the concurrency
> approach and the security limitation above.

1. _Question 1_ — …
2. _Question 2_ — …
3. _Question 3_ — …
4. _Question 4_ — …
