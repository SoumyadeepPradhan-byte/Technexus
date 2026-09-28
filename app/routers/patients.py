"""
app/routers/patients.py  –  PATIENTS, HEALTH RECORDS, PRESCRIPTIONS
=====================================================================
GET /patients/{id}/bundle  is the offline-first endpoint: the patient's entire file in one small JSON,
so a health worker downloads it before walking into a no-signal village.

Who can do what: patients see their own file; health workers / doctors / hospital admins see everyone
in their work. Records are never deleted (is_deleted flag) so offline copies stay consistent.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import HealthRecord, Patient, Prescription, User
from app.schemas import PatientCreate, PatientOut, PrescriptionOut, RecordCreate, RecordOut
from app.services.integration import log_event

router = APIRouter(prefix="/patients", tags=["Patients & Health Records"])
STAFF = require_roles("health_worker", "doctor", "hospital_admin")


def _patient_or_404(db, pid) -> Patient:
    p = db.get(Patient, pid)
    if not p or p.is_deleted:
        raise HTTPException(404, "Patient not found")
    return p


def _can_view(user: User, p: Patient):
    if user.role in ("admin", "health_worker", "doctor", "hospital_admin"):
        return
    if user.role == "patient" and p.user_id == user.id:
        return
    raise HTTPException(403, "Not your record")


@router.get("", response_model=list[PatientOut])
def list_patients(region_id: int | None = None, village: str | None = None, search: str | None = None,
                  db: Session = Depends(get_db), _: User = Depends(STAFF)):
    q = db.query(Patient).filter(Patient.is_deleted.is_(False))
    if region_id:
        q = q.filter(Patient.region_id == region_id)
    if village:
        q = q.filter(Patient.village.ilike(f"%{village}%"))
    if search:
        q = q.filter(Patient.name.ilike(f"%{search}%") | Patient.phone.ilike(f"%{search}%"))
    return q.order_by(Patient.name).limit(200).all()


@router.post("", response_model=PatientOut, status_code=201)
def create_patient(data: PatientCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Health workers register villagers; a patient user can also register themselves."""
    if data.client_id and db.query(Patient).filter_by(client_id=data.client_id).first():
        raise HTTPException(409, "client_id already exists (use /sync/push for updates)")
    p = Patient(**data.model_dump(), registered_by=user.id, user_id=user.id if user.role == "patient" else None)
    if user.role == "patient" and not p.phone:
        p.phone = user.phone
    db.add(p); db.commit(); db.refresh(p)
    log_event(db, "patients", f"patient registered: {p.name} ({p.village})", f"by {user.role} #{user.id}")
    db.commit()
    return p


@router.get("/me", response_model=PatientOut)
def my_patient(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.query(Patient).filter_by(user_id=user.id).first()
    if not p:
        raise HTTPException(404, "No patient profile linked to this login")
    return p


@router.get("/{patient_id}", response_model=PatientOut)
def get_patient(patient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _patient_or_404(db, patient_id)
    _can_view(user, p)
    return p


@router.get("/{patient_id}/bundle")
def offline_bundle(patient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """The whole patient file in one compact response - cache it on the phone before losing signal."""
    p = _patient_or_404(db, patient_id)
    _can_view(user, p)
    records = db.query(HealthRecord).filter_by(patient_id=p.id, is_deleted=False).order_by(HealthRecord.created_at.desc()).all()
    rx = db.query(Prescription).filter_by(patient_id=p.id, is_deleted=False).order_by(Prescription.created_at.desc()).all()
    return {"patient": PatientOut.model_validate(p), "records": [RecordOut.model_validate(r) for r in records],
            "prescriptions": [PrescriptionOut.model_validate(x) for x in rx]}


@router.get("/{patient_id}/records", response_model=list[RecordOut])
def records(patient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _patient_or_404(db, patient_id)
    _can_view(user, p)
    return db.query(HealthRecord).filter_by(patient_id=p.id, is_deleted=False).order_by(HealthRecord.created_at.desc()).all()


@router.post("/{patient_id}/records", response_model=RecordOut, status_code=201)
def add_record(patient_id: int, data: RecordCreate, db: Session = Depends(get_db), user: User = Depends(STAFF)):
    p = _patient_or_404(db, patient_id)
    r = HealthRecord(patient_id=p.id, recorded_by=user.id, **data.model_dump())
    db.add(r); db.commit(); db.refresh(r)
    return r


@router.get("/{patient_id}/prescriptions", response_model=list[PrescriptionOut])
def prescriptions(patient_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = _patient_or_404(db, patient_id)
    _can_view(user, p)
    return db.query(Prescription).filter_by(patient_id=p.id, is_deleted=False).order_by(Prescription.created_at.desc()).all()
