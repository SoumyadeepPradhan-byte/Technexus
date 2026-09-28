# TechNexus – Telehealth Bridge for Underserved Rural Areas (Backend)

> **New here? Read [`START_HERE.md`](START_HERE.md) first** – a beginner's walkthrough of every file, how to run it, how to add endpoints, and common errors.

Problem statement **CB-SW-08**. FastAPI + SQLAlchemy + JWT. Multilingual (English / Hindi / Odia), low-bandwidth (gzip, tiny payloads, video→audio→text by measured network), offline-first (client-id sync with conflict handling), and scalable by district.

## Run it – easiest: double-click `start.bat`

First run installs everything and creates demo data. Every run after that starts the server and opens Swagger.
`reset-data.bat` = fresh demo data. `run-tests.bat` = the 69 end-to-end checks.

## Run it – VS Code

Open the `backend` folder → `Ctrl+Shift+P` → **Run Task** → `1) Setup` → `2) Seed demo data` → press **F5**.
Test endpoints by clicking *Send Request* in `requests.http`.

## Run it – terminal (Windows PowerShell)

```powershell
cd technexus\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python seed.py
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger: http://localhost:8000/docs (click **Authorize**, username = phone number or email)

| Login | Role | Password |
|---|---|---|
| admin@technexus.io | admin | 1234 |
| 9000000001 | hospital_admin | 1234 |
| 9000000010 | health_worker (ASHA, Kalahandi) | 1234 |
| 9000000011 | health_worker (Bastar) | 1234 |
| 9000000020 | pharmacist | 1234 |
| 9000000030 | patient (Laxmi Nayak) | 1234 |
| 9000000040 | doctor (general medicine, speaks Odia) | 1234 |
| 9000000041 | doctor (pediatrics) | 1234 |

## The 3-minute demo

1. `GET /triage/understand?text=bukhar aur khansi` → the AI reads Hinglish. Try Odia script too.
2. `POST /demo/patient-journey` → one response shows: fever+cough for 4 days → **AI says urgent** → **best Odia-speaking doctor matched** → **appointment booked as AUDIO because the phone is on 120 kbps** → doctor completes consult → **medicines reserved at the nearest government pharmacy** → **SMS in Odia** → **trip avoided, ₹450 saved** recorded.
3. `POST /demo/emergency` → chest pain in Odia → **EMERGENCY**: nearest hospital with emergency care alerted, IVR call queued, *no booking* — the clear escalation path the PS asks for.
4. `POST /demo/offline-sync` → a health worker's phone syncs 2 patients + vitals + a triage done with zero signal; the triage gets evaluated on arrival.
5. `GET /analytics/impact` → trips avoided, km and ₹ saved, wasted trips prevented, avg wait, per district (Kalahandi + Bastar = two states = replicable).
6. `GET /events` → every automatic action, timestamped.

## How the PS's evaluation criteria map to code

| Evaluation focus | Where it is |
|---|---|
| Offline / low-bandwidth robustness | `POST /sync/push` & `/pull` (client_id, newer-wins, conflicts returned); `GET /patients/{id}/bundle`; GZip on every response; `GET /network/recommend-mode` |
| Multilingual & accessibility | `app/ai/language.py` – symptom aliases in Hindi/Odia/Hinglish; all advice & SMS in the patient's language; `GET /i18n/{lang}`; phone + 4-digit PIN login; IVR (voice) channel for emergencies |
| Clinical safety of symptom checker | `app/ai/triage.py` – red-flag table, vitals override, vulnerable groups bumped up, self-care always says "see a doctor if…", unknown symptoms never reassured, emergencies escalate instead of booking |
| Real-world integration | Doctor availability slots (`/doctors/{id}/slots`), pharmacist stock updates (`PUT /pharmacy/{id}/stock`) with "last updated" timestamps |
| Scalability & replicability | `Region` table; `POST /regions` adds a district; all data hangs off `region_id`; seeded across two states |
| Measurable impact | `ImpactEvent` table, `GET /analytics/impact`, `/analytics/region/{id}` |

## API map (`/api/v1`)

| Module | Endpoints |
|---|---|
| Auth | `POST auth/register`, `POST auth/login`, `GET auth/me`, `GET auth/users`, `GET auth/roles` |
| Regions & languages | `regions` (GET/POST), `GET hospitals`, `GET languages`, `GET i18n/{lang}` |
| Patients | `patients` (GET/POST), `GET patients/me`, `GET patients/{id}`, `GET patients/{id}/bundle`, `patients/{id}/records` (GET/POST), `GET patients/{id}/prescriptions` |
| Doctors | `GET doctors`, `GET doctors/available` (AI ranked), `GET doctors/me`, `POST doctors/me/online`, `doctors/{id}/slots` (GET/POST) |
| Appointments | `GET network/recommend-mode`, `appointments` (GET/POST), `POST appointments/{id}/cancel`, `POST consultations/{ap}/start`, `POST consultations/{id}/complete`, `GET consultations` |
| Pharmacy | `GET pharmacy/medicines?q=`, `GET pharmacy`, `GET pharmacy/availability/{medicine}`, `pharmacy/{id}/stock` (GET/PUT), `pharmacy/reservations` (GET/POST), `POST pharmacy/reservations/{id}/collect` |
| Triage | `POST triage`, `GET triage/understand`, `GET triage/history` |
| Sync | `POST sync/push`, `POST sync/pull`, `GET sync/status` |
| Impact | `GET analytics/impact`, `GET analytics/region/{id}`, `GET notifications`, `GET events` |
| Demo | `POST demo/patient-journey`, `POST demo/emergency`, `POST demo/offline-sync` |

## Roles
`admin` · `patient` · `doctor` · `health_worker` (ASHA/CHW) · `pharmacist` · `hospital_admin`. Enforced with `require_roles(...)` in `app/core/deps.py`.

## Where the AI lives – contract for the AI/ML teammate
`app/ai/*.py` – pure functions, dicts in / dicts out, **no DB access**. Replace the internals, keep the signatures:

| Function | v0 (works now) | Upgrade to |
|---|---|---|
| `triage.assess_symptoms(...)` | readable red-flag rules + vitals + vulnerable groups | ML classifier / LLM **behind** the same guardrails (never instead of them) |
| `language.normalize_symptoms(text)` | alias dictionary (en/hi/or + Hinglish) | embedding search / IndicBERT so misspellings still map |
| `language.translate(key, lang)` | string tables | IndicTrans2 / LLM for free-text |
| `bandwidth.recommend_mode(kbps, latency, loss)` | thresholds | learn from dropped-call history per village |
| `matching.rank_doctors(...)` | weighted score | learn weights from outcomes / no-shows |

## Project layout
```
app/
  main.py            FastAPI app, GZip, CORS, router registration
  core/              config (.env), database, security (bcrypt+JWT), deps (auth + RBAC)
  models/            SQLAlchemy tables – core, patients, clinical, pharmacy, support
  schemas/           Pydantic request/response models
  routers/           one file per module
  services/integration.py   ← every cross-module chain lives here
  ai/                AI/ML contract (swap internals, keep signatures)
seed.py              demo data (Kalahandi + Bastar)
smoke_test.py        69 end-to-end checks
```

## Video/audio calls
The backend issues a `room_id` per consultation. The frontend opens that room in any WebRTC service (Jitsi Meet is free: `https://meet.jit.si/<room_id>`) at the bitrate from `/network/recommend-mode`. Media never touches this server, which is what keeps it cheap and low-bandwidth.

## Switching to PostgreSQL
Set `DATABASE_URL=postgresql+psycopg2://user:pass@host/db` in `.env`, `pip install psycopg2-binary`, run `python seed.py`.
