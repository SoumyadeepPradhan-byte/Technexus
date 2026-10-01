"""
app/routers/ai.py  –  ROUTER FOR AI WORKFLOWS
================================================
Exposes dedicated endpoints for:
  - POST /api/v1/ai/triage: Medical/symptom triage with clinical guardrails
  - POST /api/v1/ai/patient-summary: Multi-record patient summary generation
  - POST /api/v1/ai/doctor-notes: SOAP note and prescription drafting
  - GET  /api/v1/ai/status: AI subsystem diagnostic status and provider info
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Patient, User
from app.schemas.ai import (
    AIDoctorNoteDraftRequest,
    AIDoctorNoteDraftResponse,
    AIHealthStatusOut,
    AIMedicalTriageRequest,
    AIMedicalTriageResponse,
    AIPatientSummaryRequest,
    AIPatientSummaryResponse,
)
from app.services.ai import (
    draft_doctor_notes_ai,
    generate_patient_summary_ai,
    get_ai_service_status,
    triage_medical_symptoms_ai,
)

router = APIRouter(prefix="/ai", tags=["AI Workflows"])


@router.post("/triage", response_model=AIMedicalTriageResponse)
def medical_triage_endpoint(
    data: AIMedicalTriageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Evaluates patient symptoms, vital signs, and history using structured AI triage.
    Clinical safety invariants:
      - Emergency symptoms (chest pain, severe dyspnea, SpO2 < 90%) trigger emergency escalation.
      - Vulnerable demographics (under 5, over 65, pregnancy) are safeguarded against under-triage.
      - Seamless fallback to deterministic clinical rules if external LLM times out or is offline.
    """
    return triage_medical_symptoms_ai(db=db, request=data, caller=user)


@router.post("/patient-summary", response_model=AIPatientSummaryResponse)
def patient_summary_endpoint(
    data: AIPatientSummaryRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Synthesizes health records, vitals trends, triage checks, and active prescriptions
    into a structured clinical handover summary.
    """
    if data.patient_id:
        p = db.get(Patient, data.patient_id)
        if not p or p.is_deleted:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Patient not found")
        # RBAC: patients can only access their own summary; staff can view all
        if user.role not in ("admin", "health_worker", "doctor", "hospital_admin"):
            if user.role == "patient" and p.user_id != user.id:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to access this patient's records")

    return generate_patient_summary_ai(db=db, request=data, caller=user)


@router.post("/doctor-notes", response_model=AIDoctorNoteDraftResponse)
def doctor_notes_endpoint(
    data: AIDoctorNoteDraftRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Generates a structured SOAP clinical encounter note (Subjective, Objective, Assessment, Plan),
    electronic prescription suggestions, and plain-language patient counseling instructions.
    """
    # Doctors, health workers, and administrators can draft consultation notes
    if user.role not in ("admin", "doctor", "health_worker", "hospital_admin"):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only clinical staff (doctor, health worker, admin) can draft clinical encounter notes"
        )
    return draft_doctor_notes_ai(db=db, request=data, caller=user)


@router.get("/status", response_model=AIHealthStatusOut)
def ai_status_endpoint():
    """
    Health check and telemetry diagnostics for the AI subsystem.
    Publicly accessible to monitor active provider, model name, and fallback engine status.
    """
    return get_ai_service_status()
