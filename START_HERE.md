# START HERE – Sunena's guide to this backend

Read this once, top to bottom (15 minutes). After that you'll be able to explain every file to the judges and add your own endpoints.

Good news first: **you were building the right thing.** Your "Telehealth Bridge API" matched problem statement CB-SW-08 exactly. This is the same idea, finished and tested, with the parts the judges score (offline sync, multilingual triage, pharmacy availability, impact numbers) built in.

---

## 0. Why "technexus"?

Your VS Code showed `C:\Users\DELL\Desktop\technexus\backend` – that's your team's folder. The zip is named to drop straight in. Nothing in the code depends on the folder name. To change the title on the Swagger page, edit `APP_NAME` in `app/core/config.py`.

---

## 1. Run it – the easy way

Double-click **`start.bat`**. First time it installs everything; after that it just starts the server and opens Swagger in your browser. Close the black window to stop. `reset-data.bat` gives you fresh demo data before a demo.

Log in with the green **Authorize** button → username `9000000010` (the ASHA health worker), password `1234`. Other logins are in the README.

That's enough to work. The VS Code steps below are for when you want to edit code with autocomplete and breakpoints.

## 1b. Run it in VS Code

1. Open **the `backend` folder** in VS Code (File ▸ Open Folder). Not `technexus` – the `backend` inside it.
2. Accept "install recommended extensions".
3. `Ctrl+Shift+P` → **Run Task** → `1) Setup (first time only)` → wait for "Setup done".
4. Run Task → `2) Seed demo data`.
5. Press **F5** → `▶ Run API (auto-reload)`. Terminal shows `Uvicorn running on http://0.0.0.0:8000`.
6. Open http://localhost:8000/docs → Authorize → `9000000010` / `1234`.
7. Open `requests.http` → click **Send Request** above `### 1. Login`, then above any other block.

---

## 2. What a backend is (30-second version)

The frontend is a pretty page. It can't remember anything. It sends **HTTP requests** to us:

```
App on the ASHA's phone                         Backend (this project)
"POST /triage {symptoms: 'bukhar aur khansi'}"  →  AI reads Hindi → "urgent, see a doctor today" (in Odia)
"GET  /pharmacy/availability/1"                 →  read DB → "Jan Aushadhi Bhawanipatna has 40, ₹1.2"
"POST /sync/push {records created offline}"     →  save them, return server ids, flag conflicts
```

An **endpoint** = one URL + one method (GET = read, POST = create, PUT/PATCH = change). Swagger (`/docs`) is the auto-generated manual.

---

## 3. How one request travels through the code

Take `POST /api/v1/triage`:

```
1. app/main.py                 uvicorn receives it, FastAPI finds the router
2. app/routers/triage.py       def triage(data: TriageRequest, db=..., user=Depends(get_current_user))
      ├─ TriageRequest (app/schemas)   validates the JSON (age 0-120, duration ≥ 0…)
      ├─ Depends(get_db)               gives a DB session
      └─ Depends(get_current_user)     checks the token; not logged in? 401, stop.
3.    └─ calls run_triage()   (app/services/integration.py)
            ├─ assess_symptoms()   (app/ai/triage.py)     ← the AI
            │     └─ normalize_symptoms() (app/ai/language.py)  "bukhar" → "fever"
            ├─ saves a TriageResult (app/models/support.py)
            ├─ emergency? → escalate_emergency(): hospital SMS, IVR call, impact event
            └─ auto_book? → book_appointment(): rank_doctors() → slot → mode by bandwidth → SMS
4. FastAPI turns the result into JSON → back to the phone
```

Every endpoint follows this shape. Once you've read one router, you've read them all.

---

## 4. File map – read in THIS order

| # | File | What it is | Time |
|---|---|---|---|
| 1 | `app/main.py` | The front door. GZip, CORS, registers modules. | 2 min |
| 2 | `app/core/config.py` | Settings + the rules (languages, emergency number, bandwidth threshold). | 1 min |
| 3 | `app/core/database.py` | How we connect to SQLite. `get_db()` explained. | 2 min |
| 4 | `app/core/security.py` | Password hashing + JWT tokens. | 2 min |
| 5 | `app/core/deps.py` | "Logged in? Right role?" | 2 min |
| 6 | `app/models/patients.py` | The offline-sync columns (client_id, version…) explained. | 3 min |
| 7 | `app/models/*.py` | The other tables. | 3 min |
| 8 | `app/schemas/__init__.py` | JSON shapes in and out. | 2 min |
| 9 | `app/routers/triage.py` | A small router. | 2 min |
| 10 | `app/routers/appointments.py` | A typical router. | 3 min |
| 11 | **`app/services/integration.py`** | **The heart. The patient journey, sync, escalation.** | 10 min |
| 12 | `app/ai/triage.py` + `language.py` | The symptom checker and the multilingual layer. | 5 min |
| 13 | `seed.py` / `smoke_test.py` | Demo data / the tests. | skim |

Every file starts with a comment block explaining itself. Trust those.

---

## 5. The PS's five features and where each lives

| Problem statement asks for | Tables | Endpoints | AI |
|---|---|---|---|
| Multilingual video consultation | clinical.py (Doctor, Slot, Appointment, Consultation) | `/doctors/available`, `/appointments`, `/consultations/*`, `/network/recommend-mode` | matching.py, bandwidth.py |
| Offline-accessible health records | patients.py (client_id / version columns) | `/patients/{id}/bundle`, `/sync/push`, `/sync/pull` | – |
| Real-time medicine availability | pharmacy.py | `/pharmacy/availability/{id}`, `PUT /pharmacy/{id}/stock`, `/pharmacy/reservations` | – |
| Low-bandwidth AI symptom checker | support.py (TriageResult) | `/triage`, `/triage/understand` | triage.py, language.py |
| Scalability by design | core.py (Region) | `/regions`, `/analytics/region/{id}` | – |

---

## 6. Add your own endpoint (worked example, 5 minutes)

Let's add `GET /api/v1/patients/{patient_id}/summary` – patient + how many triages and appointments they've had.

**Step 1 – open `app/routers/patients.py`, add at the bottom:**

```python
@router.get("/{patient_id}/summary")
def patient_summary(patient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _patient_or_404(db, patient_id)                 # 404 if missing
    _can_view(user, p)                                  # 403 if not allowed
    from app.models import Appointment, TriageResult    # (normally imports go at the top)
    return {"id": p.id, "name": p.name, "village": p.village,
            "triages": db.query(TriageResult).filter_by(patient_id=p.id).count(),
            "appointments": db.query(Appointment).filter_by(patient_id=p.id).count()}
```

**Step 2 – save.** The server auto-reloads. Refresh `/docs` → your endpoint is there. Try it with patient_id = 1.

**Step 3 – add a test** at the end of `smoke_test.py`, before the final `print`:

```python
r = c.get(f"{B}/patients/1/summary", headers=asha)
check("patient summary endpoint", r.status_code == 200 and "triages" in r.json())
```

Run `run-tests.bat` → `70 passed`. That's the whole development loop.

**Want a new table?** Add a class in `app/models/<file>.py`, import it in `app/models/__init__.py`, add `XxxCreate`/`XxxOut` in schemas, then re-run `seed.py`.

---

## 7. Common errors and the fix

| You see | Fix |
|---|---|
| `email-validator is not installed` | already in requirements.txt – run task 1 / `start.bat` again |
| `running scripts is disabled on this system` | PowerShell: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, answer Y (only needed for setup.ps1; start.bat doesn't need it) |
| `ModuleNotFoundError: No module named 'app'` | Terminal is in the wrong folder. `cd backend` (where `app/` is) |
| `No module named fastapi` | venv not active. Use F5 or start.bat (they use the venv automatically) |
| `[Errno 10048] address already in use` | Old server still running. Close its window, or use `--port 8001` |
| `401 Unauthorized` in Swagger | Click Authorize again |
| `403 Forbidden` | Right login, wrong role. E.g. a patient can't update pharmacy stock |
| `409 Conflict` on booking | No doctor with free slots for that specialty – run `reset-data.bat` |
| `422 Unprocessable Entity` | JSON doesn't match the schema; the response says which field |
| weird DB error after editing a model | delete `telehealth.db`, run seed again |

---

## 8. Glossary

- **FastAPI** – the Python web framework. Turns functions into endpoints, writes Swagger for free.
- **uvicorn** – the server that runs FastAPI.
- **Router** – a file grouping related endpoints, one per module.
- **Pydantic / schema** – validates JSON in and out.
- **SQLAlchemy / ORM / model** – tables as Python classes.
- **Session (`db`)** – one conversation with the database: `db.add()`, `db.commit()`, `db.query()`.
- **`Depends()`** – "run this helper first, give me the result" – DB sessions, login checks.
- **JWT** – the login token. Lasts 30 days here so villagers don't re-login on bad networks.
- **RBAC** – role-based access control. `require_roles("doctor")`.
- **client_id** – a UUID the phone makes itself, so offline records have an identity before the server sees them.
- **Conflict (sync)** – two devices edited the same record; newer wins, the loser is returned, never silently lost.
- **GZip** – responses are compressed; a 60 KB JSON becomes ~8 KB on a 2G link.
- **IVR** – an automated voice call. Emergencies use it so a person who can't read still gets the message.
- **Seed** – fill the DB with realistic fake data. **Smoke test** – quick "does everything work?" run.

---

## 9. How to explain this to the judges (60 seconds)

> "The backend is FastAPI on one database, split into modules: patients and health records, doctors and availability, appointments and consultations, pharmacy stock, the AI symptom checker, offline sync, and impact analytics.
>
> Three things are built for rural reality. **Offline-first:** every record carries a client-side UUID and a version, so a health worker registers patients and runs triage with no signal, then `/sync/push` merges it later – newer wins, conflicts come back, nothing is silently lost. **Low bandwidth:** every response is gzip-compressed, pull only sends what changed since last sync, and the app measures its network and we pick video, audio or text automatically. **Multilingual and safe:** the triage reads symptoms typed in Hindi, Odia, or Hinglish, answers in the patient's language, and has hard red-flag rules – chest pain, breathlessness, snake bite, low SpO2 – that always escalate to the nearest emergency hospital and never book a routine appointment. Children under five, over-65s and pregnant women are bumped up a level. A doctor can read the rules and sign off on them.
>
> Every automatic action is logged; `/analytics/impact` shows trips avoided, rupees saved, wasted trips prevented, per district – and adding a district is one row."

Then run `POST /demo/patient-journey` and `POST /demo/emergency` live.

---

## 10. Splitting work with the team

- **AI/ML teammate:** `app/ai/` – five functions with docstrings saying inputs, outputs and the upgrade path. She changes the *insides* only. The rule: ML goes **behind** the red-flag guardrails in `triage.py`, never replaces them. Run `run-tests.bat` after – still 69 passing = safe.
- **Frontend teammate:** `POST /auth/login` with `{phone_or_email, password}` → token. `GET /i18n/{lang}` for all UI strings. `GET /patients/{id}/bundle` for offline cache. `GET /network/recommend-mode` before starting a call, then open `room_id` in Jitsi. `POST /sync/push` / `pull` for offline mode.
- **Admin:** push the `backend` folder to the repo. `.gitignore` excludes `.venv`, `.env`, `*.db`.
- **You, later, with AI help:** open the folder in Antigravity, Claude Code or Cursor. `AGENTS.md` / `CLAUDE.md` tell the AI the rules. Ask for one endpoint at a time; run the tests after each.

You had the right idea from the start. Now it's finished. Go show them.
