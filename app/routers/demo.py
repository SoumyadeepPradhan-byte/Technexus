"""
app/routers/demo.py  –  ONE ENDPOINT FOR THE PITCH
====================================================
POST /demo/patient-journey   runs the whole story in one call and returns every step:
   villager with fever+cough for 4 days (typed in Hindi) → AI says "urgent" → best Odia-speaking doctor found
   → appointment booked as AUDIO because network is 120 kbps → doctor completes consult with a prescription
   → medicines reserved at the nearest government pharmacy → SMS in Odia → impact recorded.
POST /demo/emergency         chest pain in Odia → EMERGENCY → nearest hospital alerted, IVR call queued, no booking.
POST /demo/offline-sync      a health worker's phone pushes 2 patients + a triage done offline → server ids returned.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Consultation, Doctor, EventLog, Notification, Patient, User
from app.schemas import EventOut, NotificationOut
from app.services.integration import complete_consultation, run_triage, start_consultation, sync_push, utcnow

router = APIRouter(prefix="/demo", tags=["Demo"])


def _trail(db, start_id):
    return [EventOut.model_validate(e) for e in db.query(EventLog).filter(EventLog.id > start_id).order_by(EventLog.id).all()]


def _sms(db, phone):
    return [NotificationOut.model_validate(n) for n in db.query(Notification).filter_by(phone=phone).order_by(Notification.id.desc()).limit(3).all()]


@router.post("/patient-journey")
def patient_journey(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    start = db.query(EventLog).count()
    p = db.query(Patient).filter(Patient.village == "Lanjigarh").first() or db.query(Patient).first()
    tr, result, ap = run_triage(db, {"symptoms": "bukhar aur khansi", "age": p.age, "duration_days": 4, "patient_id": p.id,
                                     "auto_book": True, "network_kbps": 120, "latency_ms": 350}, user)
    steps = {"1_triage": {"input": "bukhar aur khansi (4 days)", "urgency": result["urgency"],
                          "specialty": result["recommended_specialty"], "advice": result["recommended_action"]}}
    if ap:
        doc = db.get(Doctor, ap.doctor_id)
        steps["2_appointment"] = {"doctor": doc.user.name, "specialty": doc.specialty, "languages": doc.languages,
                                  "mode": ap.mode, "why_this_mode": "120 kbps → audio", "scheduled_at": ap.scheduled_at}
        doc_user = doc.user
        c = start_consultation(db, ap, 120, 350)
        from app.models import Medicine
        meds = db.query(Medicine).filter(Medicine.name.in_(["Paracetamol 500mg", "Amoxicillin 500mg"])).all()
        out = complete_consultation(db, c, {"notes": "Viral fever with bronchitis. Chest clear.", "diagnosis": "Acute bronchitis",
                                            "advice": "Steam inhalation, fluids", "follow_up_days": 5,
                                            "prescription_items": [{"medicine_id": m.id, "dosage": "500 mg", "frequency": "1-0-1",
                                                                    "duration_days": 5, "quantity": 10, "instructions": "after food"} for m in meds]},
                                    doc_user)
        steps["3_consultation"] = {"room_id": c.room_id, "mode": c.mode, "diagnosis": c.diagnosis, "wait_minutes": c.wait_minutes}
        steps["4_pharmacy"] = {"reserved": [{"medicine_id": r.medicine_id, "pharmacy_id": r.pharmacy_id, "expires_at": r.expires_at}
                                            for r in out["reservations"]], "unavailable": out["unavailable_medicine_ids"]}
    steps["5_sms_to_patient"] = _sms(db, p.phone)
    steps["6_what_the_system_did"] = _trail(db, start)
    return {"patient": f"{p.name}, {p.age}, {p.village} (speaks {p.language})", **steps}


@router.post("/emergency")
def emergency(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    start = db.query(EventLog).count()
    p = db.query(Patient).filter(Patient.age > 45).first() or db.query(Patient).first()
    tr, result, _ = run_triage(db, {"symptoms": "ଛାତି ବିନ୍ଧା, ଶ୍ୱାସ କଷ୍ଟ", "patient_id": p.id, "auto_book": True}, user)
    return {"patient": f"{p.name}, {p.age}, {p.village}", "input": "ଛାତି ବିନ୍ଧା, ଶ୍ୱାସ କଷ୍ଟ (Odia: chest pain, breathlessness)",
            "understood_as": result["symptoms_normalized"], "urgency": result["urgency"], "red_flags": result["red_flags"],
            "action": result["recommended_action"], "booked_appointment": False,
            "notifications": _sms(db, p.phone), "what_the_system_did": _trail(db, start)}


@router.post("/offline-sync")
def offline_sync(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    start = db.query(EventLog).count()
    ts = utcnow()
    pushed = [
        {"type": "patient", "client_id": "demo-dev-p1", "updated_at": ts,
         "data": {"name": "Sunita Majhi", "age": 29, "sex": "F", "phone": "9000000101", "village": "Thuamul Rampur", "region_id": 1, "language": "or", "is_pregnant": True}},
        {"type": "patient", "client_id": "demo-dev-p2", "updated_at": ts,
         "data": {"name": "Raju Naik", "age": 4, "sex": "M", "phone": "9000000102", "village": "Thuamul Rampur", "region_id": 1, "language": "or"}},
        {"type": "health_record", "client_id": "demo-dev-r1", "updated_at": ts,
         "data": {"patient_client_id": "demo-dev-p1", "record_type": "vitals", "title": "ASHA visit", "bp_systolic": 150, "bp_diastolic": 96, "pulse": 88}},
        {"type": "triage", "client_id": "demo-dev-t1", "updated_at": ts,
         "data": {"patient_client_id": "demo-dev-p2", "symptoms": "ଜ୍ୱର ଓ ଝାଡ଼ା", "duration_days": 2}},
    ]
    res = sync_push(db, "asha-phone-demo", pushed, user)
    return {"scenario": "Health worker registered 2 patients, recorded vitals and ran a triage in a no-signal village; phone syncs now.",
            "pushed": len(pushed), **res, "what_the_system_did": _trail(db, start)}
