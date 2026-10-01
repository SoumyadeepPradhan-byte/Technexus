"""
app/main.py  –  THE FRONT DOOR OF THE BACKEND
================================================
`uvicorn app.main:app` looks for the variable `app` in this file and serves it on port 8000.

  1. Create DB tables if missing.
  2. Create the FastAPI app (Swagger at /docs comes free).
  3. GZip every response over 500 bytes  ← LOW-BANDWIDTH: JSON shrinks 5-10x on a 2G link.
  4. CORS so the frontend on another port can call us.
  5. Plug in every module's router under /api/v1.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.core.config import settings
from app.core.database import Base, engine
import app.models  # noqa: F401  ← registers every table so create_all() knows about them
from app.routers import ai, analytics, appointments, auth, core, demo, doctors, patients, pharmacy, sync, triage

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    description=(
        "Telehealth Bridge for Underserved Rural Areas - multilingual, low-bandwidth, offline-first.\n\n"
        "Modules: Auth · Patients & offline health records · Doctors & availability · Appointments & "
        "bandwidth-aware consultations · Pharmacy medicine availability · AI symptom checker (triage) · "
        "Offline sync · Impact analytics · AI Workflows.\n\n"
        "**Login:** click *Authorize*, username = phone number. Seeded users all use password `1234`."
    ),
)
app.add_middleware(GZipMiddleware, minimum_size=settings.GZIP_MIN_BYTES)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

for r in (auth, core, patients, doctors, appointments, pharmacy, triage, sync, analytics, demo, ai):
    app.include_router(r.router, prefix=settings.API_PREFIX)


@app.get("/", tags=["Health"])
def root():
    return {"app": settings.APP_NAME, "docs": "/docs", "api": settings.API_PREFIX}


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok"}
