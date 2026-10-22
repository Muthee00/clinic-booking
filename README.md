# Clinic Booking API

A Django REST Framework API for booking, cancelling and rescheduling 30-minute clinic appointments. It supports per-doctor working hours, slot availability, and database-level protection against double booking.

- **Live API (Swagger UI):** https://clinic-booking-api-80cr.onrender.com/api/docs/
- **OpenAPI schema:** https://clinic-booking-api-80cr.onrender.com/api/schema/

> Hosted on Render's free tier. The service sleeps when idle, so the first request may take 30–60 seconds.

---

## Requirements

The clinic has 5 doctors, each with set working hours and 30-minute slots. Patients view free slots for a doctor on a given day, book one, and can cancel. A booked slot must never be available to anyone else.

| Requirement | Design approach |
|---|---|
| Doctors have set working hours | Weekly schedule stored per doctor |
| 30-minute slots | Fixed slot length on a :00 / :30 grid |
| View free slots | Availability computed from schedule minus bookings |
| No double booking | Enforced by the database, including under concurrent requests |
| Patients can cancel | Cancellation releases the slot but keeps the record |
| Room to grow | Simple monolith with clear separation of concerns |

**Assumptions**

- One clinic, one timezone (`Africa/Nairobi`).
- A doctor can have several working blocks per day (e.g. a lunch break).
- Bookings must be made at least 1 hour in advance and never in the past.
- A patient cannot hold two appointments at the same time.
- Rescheduling moves an existing appointment to a new slot in a single transaction.

---

## Design

### Structure

```
Request → View → Serializer (input validation) → services.py (business rules) → Models / DB constraints
```

| Component | Responsibility |
|---|---|
| `doctors` app | Doctors, working hours, availability endpoint |
| `appointments` app | Patients and appointments: booking, cancelling, rescheduling |
| `appointments/services.py` | All business rules, transactions and locking |
| Database constraints | Final guarantee against double booking |
| drf-spectacular | OpenAPI schema and Swagger UI |

### Models

| Model | Key fields |
|---|---|
| `Doctor` | `name`, `specialization`, `is_active` |
| `DoctorWorkingHour` | `doctor`, `weekday`, `start_time`, `end_time` |
| `Patient` | `name`, `email` (unique) |
| `Appointment` | `doctor`, `patient`, `starts_at`, `ends_at`, `status` (`booked` / `cancelled`), `cancellation_reason` |

### Key decisions

1. **Slots are computed, not stored.** Availability is derived from the doctor's working hours minus existing bookings, so there is a single source of truth and no data to keep in sync.
2. **Double booking is prevented by the database.** A partial unique index on `(doctor, starts_at)` where `status = 'booked'` allows only one active booking per slot. A matching index on `(patient, starts_at)` prevents a patient from double-booking themselves.
3. **Concurrency is handled safely.** Bookings run inside a transaction and lock the doctor row. If a race still occurs, the unique index rejects the second booking and the API returns **409 Conflict**.
4. **Cancellation is a status change, not a delete.** This keeps an audit trail and automatically frees the slot.
5. **Business rules live in one place** (`services.py`), keeping views thin and rules easy to test.
6. **The server controls time.** Clients send only the start time; the server calculates the end time and validates it.

### Future improvements

- Authentication, user roles and object-level permissions
- Doctor time off and holidays
- Email/SMS notifications via a background queue
- Support for multiple clinics and variable appointment lengths
- Pagination, caching and rate limiting

---

## Business rules

1. Appointments last exactly 30 minutes and must start on a :00 or :30 boundary.
2. The doctor must be active and the slot must fall within their working hours.
3. Past slots and slots less than 1 hour away are rejected.
4. Overlapping bookings for the same doctor or patient return **409**.
5. Cancellation requires a reason; cancelling twice returns **409**.
6. Cancelled appointments cannot be rescheduled (**409**).
7. Rescheduling is atomic: if the new slot is invalid, the original booking is unchanged.

### Status codes

| Status | Meaning |
|---|---|
| 200 / 201 | Success |
| 400 | Invalid input or rule violation (e.g. outside working hours, too soon) |
| 404 | Doctor, patient or appointment not found |
| 409 | Slot already taken, or invalid state (e.g. already cancelled) |

Errors return `{"detail": "...", "code": "..."}`.

---

## API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/api/doctors/` | List doctors and working hours |
| GET | `/api/doctors/<id>/availability/?date=YYYY-MM-DD` | Available slots for a day |
| POST | `/api/patients/` | Register a patient |
| POST | `/api/appointments/` | Book an appointment |
| PATCH | `/api/appointments/<id>/cancel/` | Cancel an appointment |
| PATCH | `/api/appointments/<id>/reschedule/` | Reschedule an appointment |
| GET | `/api/patients/<id>/appointments/` | Upcoming appointments for a patient |

### Example

```bash
# Check availability
curl "http://127.0.0.1:8000/api/doctors/1/availability/?date=2026-10-23"

# Book a slot
curl -X POST http://127.0.0.1:8000/api/appointments/ \
  -H "Content-Type: application/json" \
  -d '{"doctor": 1, "patient": 1, "date": "2026-10-23", "time": "09:00"}'

# Cancel
curl -X PATCH http://127.0.0.1:8000/api/appointments/1/cancel/ \
  -H "Content-Type: application/json" \
  -d '{"cancellation_reason": "Patient is travelling"}'
```

---

## Tech stack

Python 3.14 · Django 6.1 · Django REST Framework 3.18 · drf-spectacular · PostgreSQL (production) / SQLite (local) · Gunicorn · WhiteNoise · GitHub Actions · Render

---

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # set DJANGO_SECRET_KEY
python manage.py migrate
python manage.py seed_clinic       # 5 doctors, working hours, 2 demo patients
python manage.py runserver
```

Then open http://127.0.0.1:8000/api/docs/.

### Environment variables

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Django secret key (required in production) |
| `DJANGO_DEBUG` | Debug mode (default `False`) |
| `DJANGO_ALLOWED_HOSTS` | Allowed hosts |
| `DATABASE_URL` | PostgreSQL URL; uses SQLite if unset |
| `TIME_ZONE` | Clinic timezone (default `Africa/Nairobi`) |

### Tests

```bash
python manage.py test
```

31 tests cover booking, double-booking prevention, working-hour and time rules, cancellation, rescheduling, availability, and the API documentation endpoint.

---

## CI/CD and deployment

- **CI (GitHub Actions):** runs on every push and pull request to `main`. Tests run on both SQLite and PostgreSQL, along with deployment checks, a missing-migrations check and OpenAPI schema validation.
- **CD (Render):** Render deploys `main` automatically, but only after CI passes. On deploy it installs dependencies, collects static files, runs migrations, seeds demo data and starts Gunicorn.
- **Health check:** traffic switches to a new version only once `/api/doctors/` responds.
- **Secrets** are managed by Render and are not stored in the repository.

---

## Known limitations

- No authentication or authorisation.
- Past appointments can still be cancelled or rescheduled (no `completed` / `no_show` status yet).
- No pagination on list endpoints.
- Doctor working hours are managed through the Django admin, not the API.

---

## AI reflection

### 1. What did you use AI for across the four sections?

- **Section 1 – System Design:** I used AI to help break down the requirements, plan the system architecture, identify the core models, and outline the API endpoints.
- **Section 2 – API Implementation:** I used AI to speed up the initial Django REST Framework setup, generate a working prototype, structure the modules, assist with debugging, and write automated tests for the booking logic.
- **Section 3 – Deployment and CI/CD:** I used AI to help plan the configuration and deployment process and to document the steps required to run the application.
- **Section 4 – Documentation and Reflection:** I used AI to help draft the README, articulate the design decisions, and organize the project documentation.

Overall, AI reduced the time I spent on repetitive setup and documentation, which allowed me to focus on implementation, testing, and verifying that the application behaved correctly.

### 2. Give one example where an AI suggestion improved your work. What did you prompt it with?

AI helped me scaffold the project modules and produce a working prototype quickly. This gave me a functional starting point rather than building every component from scratch.

My prompt asked it to set up a Django REST Framework project for a clinic appointment booking system, organize the project into modules, implement the required endpoints, and prepare an initial set of tests.

This improved my productivity by reducing time spent on boilerplate code, so I could concentrate on the booking requirements and validation logic.

### 3. Give one example where AI output was wrong or incomplete, and how you caught it.

The AI-generated code did not fully match the project requirements. The validation logic was inconsistent with the booking rules, and the model definitions were not correct. The AI also generated endpoints that were not required for the system.

I caught these issues while reviewing the generated code against the requirements and testing the booking workflow. I corrected the validation logic, fixed the models so they reflected the intended design, and removed the unnecessary endpoints. I then retested the application to confirm that the API exposed only the required functionality and enforced the booking rules correctly.

This reinforced the importance of reviewing AI-generated code against the actual requirements rather than assuming it is complete or correct.

### 4. Name two decisions you made without AI. Why did you trust your own judgment there?

**Decision 1: Separating the date-picker output into distinct date and time values.**

I split the date-picker output into separate date and time fields to make the inputs easier to work with and to speed up manual testing. This also made it easier to test different appointment dates and time slots independently.

I trusted my judgment because I was testing the booking workflow directly and could see first-hand how this approach improved the process.

**Decision 2: Manually correcting the Swagger documentation configuration.**

The AI-generated Swagger configuration did not work as expected: the documentation dependency was installed, but the URL was not properly routed and could not be accessed. I chose to investigate and fix the configuration myself.

I trusted my judgment because I could reproduce the issue, inspect the Django URL configuration, and verify the fix by accessing the documentation endpoint. I did not consider the task complete until I had tested the result.
