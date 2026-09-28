"""
app/routers/analytics.py  –  MEASURABLE IMPACT + NOTIFICATIONS + AUDIT TRAIL
=============================================================================
GET /analytics/impact        trips avoided, km & ₹ saved, wasted trips prevented, avg wait, per region
GET /analytics/region/{id}   one district's numbers - shows the model replicates across districts
GET /notifications           the SMS/IVR queue (what the villager's phone would receive)
GET /events                  every automatic action the system took - show this to the judges
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import (Appointment, Consultation, EventLog, Hospital, ImpactEvent, Notification, Patient, Region,
                        TriageResult, User)
from app.schemas import EventOut, NotificationOut

router = APIRouter(tags=["Impact, Notifications & Audit"])


def _impact(db: Session, region_id: int | None = None) -> dict:
    q = db.query(ImpactEvent.event_type, func.count(ImpactEvent.id), func.sum(ImpactEvent.value))
    if region_id:
        q = q.filter(ImpactEvent.region_id == region_id)
    agg = {t: {"count": c, "total": round(float(s or 0), 1)} for t, c, s in q.group_by(ImpactEvent.event_type).all()}
    wait = agg.get("wait_minutes", {"count": 0, "total": 0})
    tri = db.query(TriageResult.urgency, func.count(TriageResult.id))
    if region_id:
        tri = tri.join(Patient, Patient.id == TriageResult.patient_id).filter(Patient.region_id == region_id)
    return {
        "remote_consultations": agg.get("remote_consultation", {}).get("count", 0),
        "trips_avoided": agg.get("trip_avoided", {}).get("count", 0),
        "km_saved": agg.get("trip_avoided", {}).get("total", 0),
        "rupees_saved": agg.get("money_saved", {}).get("total", 0),
        "wasted_trips_prevented": agg.get("wasted_trip_prevented", {}).get("count", 0),
        "emergencies_escalated": agg.get("emergency_escalated", {}).get("count", 0),
        "avg_wait_minutes": round(wait["total"] / wait["count"], 1) if wait["count"] else None,
        "triage_by_urgency": dict(tri.group_by(TriageResult.urgency).all()),
    }


@router.get("/analytics/impact")
def impact(db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    """Headline numbers for the whole platform + a per-region breakdown."""
    regions = db.query(Region).all()
    per_region = []
    for r in regions:
        h = db.query(Hospital).filter_by(region_id=r.id).all()
        per_region.append({"region_id": r.id, "region": r.name, "state": r.state,
                           "patients": db.query(Patient).filter_by(region_id=r.id).count(),
                           "doctor_posts_filled_pct": round(100 * sum(x.doctors_present for x in h) / max(1, sum(x.sanctioned_doctors for x in h))),
                           **_impact(db, r.id)})
    return {"overall": _impact(db), "appointments": db.query(Appointment).count(),
            "consultations_completed": db.query(Consultation).filter_by(status="completed").count(),
            "by_mode": dict(db.query(Consultation.mode, func.count(Consultation.id)).group_by(Consultation.mode).all()),
            "regions": per_region}


@router.get("/analytics/region/{region_id}")
def region(region_id: int, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    r = db.get(Region, region_id)
    if not r:
        raise HTTPException(404, "Region not found")
    return {"region": r.name, "state": r.state, **_impact(db, region_id)}


@router.get("/notifications", response_model=list[NotificationOut])
def notifications(phone: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    q = db.query(Notification)
    if user.role == "patient":
        q = q.filter(Notification.phone == user.phone)
    elif phone:
        q = q.filter(Notification.phone == phone)
    return q.order_by(Notification.created_at.desc()).limit(100).all()


@router.get("/events", response_model=list[EventOut])
def events(limit: int = 50, module: str | None = None, db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(EventLog)
    if module:
        q = q.filter(EventLog.source_module == module)
    return q.order_by(EventLog.id.desc()).limit(limit).all()
