"""
app/routers/appointments.py  –  BOOKING & CONSULTATIONS  (the video/audio/text call)
======================================================================================
POST /appointments             book. Leave doctor_id empty → AI picks the best doctor. Send the app's
                               measured network_kbps → we choose video / audio / text automatically.
POST /consultations/{ap}/start doctor joins → returns a room_id for the video app (WebRTC/Jitsi)
POST /consultations/{id}/complete  doctor's notes + prescription → health record, pharmacy reservation, SMS
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.bandwidth import recommend_mode
from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import Appointment, Consultation, Patient, User
from app.schemas import (AppointmentCreate, AppointmentOut, ConsultationComplete, ConsultationOut, ConsultationStart,
                         PrescriptionOut, ReservationOut)
from app.services.integration import book_appointment, complete_consultation, log_event, start_consultation

router = APIRouter(tags=["Appointments & Consultations"])


@router.get("/network/recommend-mode")
def recommend(kbps: float | None = None, latency_ms: float | None = None, packet_loss_pct: float | None = None):
    """The app measures its connection and asks: video, audio or text? No login needed."""
    return recommend_mode(kbps, latency_ms, packet_loss_pct, settings.LOW_BANDWIDTH_KBPS)


@router.get("/appointments", response_model=list[AppointmentOut])
def list_appointments(patient_id: int | None = None, doctor_id: int | None = None, status: str | None = None,
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Appointment).filter(Appointment.is_deleted.is_(False))
    if user.role == "patient":
        q = q.join(Patient).filter(Patient.user_id == user.id)
    if patient_id:
        q = q.filter(Appointment.patient_id == patient_id)
    if doctor_id:
        q = q.filter(Appointment.doctor_id == doctor_id)
    if status:
        q = q.filter(Appointment.status == status)
    return q.order_by(Appointment.scheduled_at.desc()).limit(200).all()


@router.post("/appointments", response_model=AppointmentOut, status_code=201)
def create_appointment(data: AppointmentCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    if user.role == "patient" and p.user_id != user.id:
        raise HTTPException(403, "You can only book for yourself")
    try:
        return book_appointment(db, p, specialty=data.specialty, doctor_id=data.doctor_id, slot_id=data.slot_id,
                                triage_id=data.triage_id, reason=data.reason, network_kbps=data.network_kbps,
                                latency_ms=data.latency_ms, booked_by=user, client_id=data.client_id)
    except ValueError as e:
        raise HTTPException(409, str(e))


@router.post("/appointments/{appointment_id}/cancel", response_model=AppointmentOut)
def cancel(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ap = db.get(Appointment, appointment_id)
    if not ap:
        raise HTTPException(404, "Appointment not found")
    if ap.status in ("completed", "cancelled"):
        raise HTTPException(400, f"Already {ap.status}")
    ap.status = "cancelled"
    if ap.slot_id:
        from app.models import AvailabilitySlot
        s = db.get(AvailabilitySlot, ap.slot_id)
        if s and s.booked > 0:
            s.booked -= 1
    log_event(db, "appointments", f"appointment #{ap.id} cancelled", f"by {user.role}")
    db.commit(); db.refresh(ap)
    return ap


@router.post("/consultations/{appointment_id}/start", response_model=ConsultationOut, status_code=201)
def start(appointment_id: int, data: ConsultationStart, db: Session = Depends(get_db),
          user: User = Depends(require_roles("doctor", "health_worker"))):
    ap = db.get(Appointment, appointment_id)
    if not ap or ap.status not in ("confirmed", "requested"):
        raise HTTPException(400, "Appointment not found or not in a startable state")
    return start_consultation(db, ap, data.network_kbps, data.latency_ms)


@router.post("/consultations/{consultation_id}/complete")
def complete(consultation_id: int, data: ConsultationComplete, db: Session = Depends(get_db),
             user: User = Depends(require_roles("doctor"))):
    """Ends the call. Returns the prescription + which medicines got reserved where."""
    c = db.get(Consultation, consultation_id)
    if not c or c.status == "completed":
        raise HTTPException(400, "Consultation not found or already completed")
    out = complete_consultation(db, c, data.model_dump(), user)
    return {"consultation": ConsultationOut.model_validate(out["consultation"]),
            "prescription": PrescriptionOut.model_validate(out["prescription"]) if out["prescription"] else None,
            "reservations": [ReservationOut.model_validate(r) for r in out["reservations"]],
            "unavailable_medicine_ids": out["unavailable_medicine_ids"]}


@router.get("/consultations", response_model=list[ConsultationOut])
def list_consultations(patient_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Consultation)
    if patient_id:
        q = q.filter(Consultation.patient_id == patient_id)
    if user.role == "doctor":
        from app.models import Doctor
        d = db.query(Doctor).filter_by(user_id=user.id).first()
        if d:
            q = q.filter(Consultation.doctor_id == d.id)
    return q.order_by(Consultation.started_at.desc()).limit(200).all()
