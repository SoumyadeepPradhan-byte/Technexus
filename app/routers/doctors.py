"""
app/routers/doctors.py  –  DOCTORS & THEIR AVAILABILITY  (hospital staff schedule integration)
=================================================================================================
GET /doctors/available?specialty=&language=  → ranked by the AI matcher: "who is the best doctor for
this patient right now" (specialty, speaks Odia, online, has free slots, same district).
Doctors toggle /doctors/me/online and publish slots; that's the "syncing with hospital staff schedules"
part of the evaluation.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import AvailabilitySlot, Doctor, User
from app.schemas import DoctorOut, SlotCreate, SlotOut
from app.services.integration import doctor_candidates, log_event, utcnow

router = APIRouter(prefix="/doctors", tags=["Doctors & Availability"])


@router.get("", response_model=list[DoctorOut])
def list_doctors(specialty: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(Doctor)
    if specialty:
        q = q.filter(Doctor.specialty == specialty)
    return q.all()


@router.get("/available")
def available(specialty: str = "general_medicine", language: str | None = None, region_id: int | None = None,
              urgency: str = "routine", db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Best-first list of doctors who can take this patient now (AI ranked)."""
    ranked = doctor_candidates(db, specialty, language or user.preferred_language, region_id or user.region_id, urgency)
    return [r for r in ranked if r["open_capacity"] > 0]


@router.get("/me", response_model=DoctorOut)
def my_profile(db: Session = Depends(get_db), user: User = Depends(require_roles("doctor"))):
    d = db.query(Doctor).filter_by(user_id=user.id).first()
    if not d:
        raise HTTPException(404, "No doctor profile for this login")
    return d


@router.post("/me/online", response_model=DoctorOut)
def set_online(online: bool = True, db: Session = Depends(get_db), user: User = Depends(require_roles("doctor"))):
    d = db.query(Doctor).filter_by(user_id=user.id).first()
    if not d:
        raise HTTPException(404, "No doctor profile for this login")
    d.is_online = online
    log_event(db, "doctors", f"Dr {user.name} is {'online' if online else 'offline'}")
    db.commit(); db.refresh(d)
    return d


@router.get("/{doctor_id}/slots", response_model=list[SlotOut])
def slots(doctor_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    return (db.query(AvailabilitySlot).filter(AvailabilitySlot.doctor_id == doctor_id, AvailabilitySlot.end_time > utcnow())
            .order_by(AvailabilitySlot.start_time).all())


@router.post("/{doctor_id}/slots", response_model=SlotOut, status_code=201)
def add_slot(doctor_id: int, data: SlotCreate, db: Session = Depends(get_db),
             user: User = Depends(require_roles("doctor", "hospital_admin"))):
    d = db.get(Doctor, doctor_id)
    if not d:
        raise HTTPException(404, "Doctor not found")
    if user.role == "doctor" and d.user_id != user.id:
        raise HTTPException(403, "You can only publish your own slots")
    s = AvailabilitySlot(doctor_id=doctor_id, start_time=data.start_time.replace(tzinfo=None),
                         end_time=data.end_time.replace(tzinfo=None), capacity=data.capacity, modes=data.modes)
    db.add(s); db.commit(); db.refresh(s)
    return s
