"""
app/routers/triage.py  –  THE AI SYMPTOM CHECKER
==================================================
POST /triage   {"symptoms": "bukhar aur khansi", "age": 34, "duration_days": 3}  → urgency + what to do,
               in the caller's language. auto_book=true → also books the best doctor (unless emergency,
               which is escalated to a hospital instead - the "clear escalation path").

Tiny request, tiny response → works on 2G. The rules are in app/ai/triage.py and are readable by a doctor.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.language import normalize_symptoms
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import TriageResult, User
from app.schemas import AppointmentOut, TriageOut, TriageRequest

router = APIRouter(prefix="/triage", tags=["AI Symptom Checker (Triage)"])


@router.post("")
def triage(data: TriageRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    from app.services.integration import run_triage
    tr, result, ap = run_triage(db, data.model_dump(), user)
    return {"triage": TriageOut.model_validate(tr), "result": result,
            "appointment": AppointmentOut.model_validate(ap) if ap else None}


@router.get("/understand")
def understand(text: str):
    """Debug/demo: see how the AI reads a symptom string in any language. No login needed."""
    return {"input": text, "symptoms": normalize_symptoms(text)}


@router.get("/history", response_model=list[TriageOut])
def history(patient_id: int | None = None, urgency: str | None = None, db: Session = Depends(get_db),
            _: User = Depends(get_current_user)):
    q = db.query(TriageResult)
    if patient_id:
        q = q.filter(TriageResult.patient_id == patient_id)
    if urgency:
        q = q.filter(TriageResult.urgency == urgency)
    return q.order_by(TriageResult.created_at.desc()).limit(200).all()
