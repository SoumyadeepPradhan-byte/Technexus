"""
app/routers/core.py  –  REGIONS, HOSPITALS, LANGUAGES  (the "scalability" and "multilingual" plumbing)
=======================================================================================================
Add a district = POST /regions. Everything else (doctors, pharmacies, patients) hangs off region_id.
GET /i18n/{lang} gives the app every UI string in that language, so the frontend never hard-codes text.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.language import STRINGS, supported_languages
from app.core.database import get_db
from app.core.deps import get_current_user, require_roles
from app.models import Hospital, Region, User
from app.schemas import HospitalOut, RegionCreate, RegionOut

router = APIRouter(tags=["Regions, Hospitals & Languages"])


@router.get("/regions", response_model=list[RegionOut])
def list_regions(db: Session = Depends(get_db)):
    return db.query(Region).order_by(Region.id).all()


@router.post("/regions", response_model=RegionOut, status_code=201)
def create_region(data: RegionCreate, db: Session = Depends(get_db), _: User = Depends(require_roles("hospital_admin"))):
    r = Region(**data.model_dump())
    db.add(r); db.commit(); db.refresh(r)
    return r


@router.get("/hospitals", response_model=list[HospitalOut])
def list_hospitals(region_id: int | None = None, emergency_only: bool = False, db: Session = Depends(get_db)):
    q = db.query(Hospital)
    if region_id:
        q = q.filter(Hospital.region_id == region_id)
    if emergency_only:
        q = q.filter(Hospital.has_emergency.is_(True))
    return q.all()


@router.get("/languages")
def languages():
    return supported_languages()


@router.get("/i18n/{lang}")
def i18n(lang: str):
    """All UI/advice strings in one language. The app downloads this once and caches it offline."""
    if lang not in STRINGS:
        raise HTTPException(404, f"language '{lang}' not supported; see /languages")
    return STRINGS[lang]
