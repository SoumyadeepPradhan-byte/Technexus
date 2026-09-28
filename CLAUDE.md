# CLAUDE.md – context for Claude Code

Backend of **TechNexus**, hackathon project for problem statement **CB-SW-08: "Telehealth Bridge for Underserved Rural Areas"**
(multilingual, low-bandwidth telemedicine: video consults, offline health records, real-time pharmacy stock,
AI symptom checker, scalable across districts). Team: Admin, Frontend, Backend (this repo), AI/ML.

## Stack
FastAPI · SQLAlchemy 2 · Pydantic v2 · SQLite (dev) · JWT (PyJWT) · bcrypt · GZipMiddleware. Python 3.11+.

## Commands
- Setup: `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt`
- Seed (wipes DB): `python seed.py`
- Run: `uvicorn app.main:app --reload --port 8000` → http://localhost:8000/docs
- Test: `python seed.py && python smoke_test.py` – must stay at 0 failures before every commit.

## Architecture rules (do not break)
1. **One shared DB.** All modules share `app/models/`. Never add a second DB.
2. **Cross-module logic lives in `app/services/integration.py` only.** Routers: validate → call service → return. Log every automation with `log_event(...)`.
3. **AI is a contract.** `app/ai/*.py` are pure functions (dicts in/out, no DB). Keep signatures + return shapes. ML models go *behind* the red-flag guardrails in `ai/triage.py`, never replace them.
4. **Clinical safety is non-negotiable.** Emergency red flags always escalate and never book a routine appointment. Vulnerable groups (age <5, >65, pregnancy) are never left at self_care. Unknown symptoms are never reassured.
5. **Offline sync invariants.** Syncable tables use `SyncMixin` (client_id, updated_at, version, is_deleted). Upsert by client_id; incoming older than server = conflict returned, never overwritten. Soft-delete only.
6. **Multilingual.** Any text shown to a patient goes through `ai/language.translate(key, lang)`; add the key to all languages in `STRINGS`. Symptom vocab lives in `SYMPTOM_ALIASES`.
7. **RBAC** via `require_roles(...)`. Roles: admin, patient, doctor, health_worker, pharmacist, hospital_admin. Patients only see their own data.
8. Datetimes stored naive-UTC; strip tzinfo on input (`.replace(tzinfo=None)`).
9. Every new feature gets a `check(...)` in `smoke_test.py`.

## Config knobs (.env / config.py)
SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE, EMERGENCY_NUMBER (108), LOW_BANDWIDTH_KBPS (300), RESERVATION_HOURS (24), GZIP_MIN_BYTES (500), ACCESS_TOKEN_EXPIRE_MINUTES (30 days).

## Likely next tasks
- Real SMS/IVR gateway behind `integration.notify()` (MSG91 / Exotel) – status flips queued→sent.
- Jitsi/WebRTC token generation for `Consultation.room_id`.
- Pagination + `?fields=` projection on list endpoints for even smaller payloads.
- Reservation expiry job (mark `expired`, return stock).
- More languages: add a column to `STRINGS` + aliases in `SYMPTOM_ALIASES`.
- Postgres for the final demo (README).

## Style
Small functions, type hints, endpoint docstrings (they render in Swagger). Keep the beginner-facing comment block at the top of every file.
