"""
app/routers/pharmacy.py  –  MEDICINE AVAILABILITY  ("don't send patients on a wasted trip")
==============================================================================================
GET  /pharmacy/medicines?q=              search in English / Hindi / Odia
GET  /pharmacy/availability/{medicine}   which pharmacies near me have it, live
PUT  /pharmacy/{id}/stock                pharmacist updates stock (one tap per delivery)
POST /pharmacy/reservations              hold medicine for a patient → SMS them where to collect
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import Medicine, MedicineReservation, Patient, Pharmacy, PharmacyStock, User
from app.schemas import MedicineOut, PharmacyOut, ReservationCreate, ReservationOut, StockUpdate
from app.services.integration import find_stock, log_event, reserve_medicine, utcnow

router = APIRouter(prefix="/pharmacy", tags=["Pharmacy & Medicine Availability"])


@router.get("/medicines", response_model=list[MedicineOut])
def medicines(q: str | None = None, db: Session = Depends(get_db)):
    query = db.query(Medicine)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Medicine.name.ilike(like), Medicine.generic_name.ilike(like),
                                 Medicine.name_hi.ilike(like), Medicine.name_or.ilike(like)))
    return query.order_by(Medicine.name).all()


@router.get("", response_model=list[PharmacyOut])
def pharmacies(region_id: int | None = None, db: Session = Depends(get_db)):
    q = db.query(Pharmacy)
    if region_id:
        q = q.filter(Pharmacy.region_id == region_id)
    return q.all()


@router.get("/availability/{medicine_id}")
def availability(medicine_id: int, region_id: int | None = None, quantity: int = 1,
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Live: which pharmacies in the district stock this medicine right now. Government pharmacies first."""
    med = db.get(Medicine, medicine_id)
    if not med:
        raise HTTPException(404, "Medicine not found")
    rows = find_stock(db, medicine_id, region_id or user.region_id, quantity)
    return {"medicine": MedicineOut.model_validate(med), "available": bool(rows),
            "pharmacies": [{"pharmacy_id": s.pharmacy_id, "name": s.pharmacy.name, "village": s.pharmacy.village,
                            "phone": s.pharmacy.phone, "is_government": s.pharmacy.is_government,
                            "quantity": s.quantity, "price": s.price, "updated_at": s.updated_at} for s in rows]}


@router.get("/{pharmacy_id}/stock")
def stock(pharmacy_id: int, db: Session = Depends(get_db)):
    rows = db.query(PharmacyStock).filter_by(pharmacy_id=pharmacy_id).all()
    return [{"medicine_id": s.medicine_id, "name": s.medicine.name, "name_hi": s.medicine.name_hi,
             "name_or": s.medicine.name_or, "quantity": s.quantity, "price": s.price, "updated_at": s.updated_at} for s in rows]


@router.put("/{pharmacy_id}/stock")
def update_stock(pharmacy_id: int, data: list[StockUpdate], db: Session = Depends(get_db),
                 user: User = Depends(require_roles("pharmacist", "hospital_admin"))):
    """Pharmacist sends [{medicine_id, quantity}] - upserts. Timestamp = 'last updated' shown to patients."""
    ph = db.get(Pharmacy, pharmacy_id)
    if not ph:
        raise HTTPException(404, "Pharmacy not found")
    if user.role == "pharmacist" and ph.owner_user_id not in (None, user.id):
        raise HTTPException(403, "Not your pharmacy")
    for u in data:
        s = db.query(PharmacyStock).filter_by(pharmacy_id=pharmacy_id, medicine_id=u.medicine_id).first()
        if not s:
            s = PharmacyStock(pharmacy_id=pharmacy_id, medicine_id=u.medicine_id, quantity=0)
            db.add(s)
        s.quantity = u.quantity
        if u.price is not None:
            s.price = u.price
        s.updated_at = utcnow()
    log_event(db, "pharmacy", f"{ph.name} updated stock for {len(data)} medicines")
    db.commit()
    return {"updated": len(data), "pharmacy": ph.name}


@router.post("/reservations", response_model=ReservationOut, status_code=201)
def reserve(data: ReservationCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    p = db.get(Patient, data.patient_id)
    if not p:
        raise HTTPException(404, "Patient not found")
    r = reserve_medicine(db, p, data.medicine_id, data.quantity, data.prescription_id, data.pharmacy_id)
    db.commit()
    if not r:
        raise HTTPException(409, "Not in stock at any nearby pharmacy; patient has been notified not to travel")
    db.refresh(r)
    return r


@router.get("/reservations", response_model=list[ReservationOut])
def reservations(patient_id: int | None = None, pharmacy_id: int | None = None, status: str | None = None,
                 db: Session = Depends(get_db), _: User = Depends(get_current_user)):
    q = db.query(MedicineReservation)
    if patient_id:
        q = q.filter_by(patient_id=patient_id)
    if pharmacy_id:
        q = q.filter_by(pharmacy_id=pharmacy_id)
    if status:
        q = q.filter_by(status=status)
    return q.order_by(MedicineReservation.created_at.desc()).all()


@router.post("/reservations/{reservation_id}/collect", response_model=ReservationOut)
def collect(reservation_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("pharmacist", "health_worker"))):
    r = db.get(MedicineReservation, reservation_id)
    if not r or r.status != "reserved":
        raise HTTPException(400, "Reservation not found or not collectable")
    r.status = "collected"
    log_event(db, "pharmacy", f"reservation #{r.id} collected")
    db.commit(); db.refresh(r)
    return r
