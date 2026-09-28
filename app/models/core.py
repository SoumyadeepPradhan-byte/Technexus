"""
app/models/core.py  –  USERS, REGIONS, HOSPITALS (shared by every module)
==========================================================================
HOW TO READ A MODEL:
    class Hospital(Base):                    → one database table called "hospitals"
        __tablename__ = "hospitals"
        id = Column(Integer, primary_key=True)     → unique row number
        name = Column(String(160), nullable=False) → text, required
        has_emergency = Column(Boolean, default=False)

Region is the "scalability by design" piece: every patient, hospital, pharmacy and doctor
belongs to a region (district). Add a new district = one row. Nothing else changes.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.core.database import Base

ROLES = ("admin", "patient", "doctor", "health_worker", "pharmacist", "hospital_admin")


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Region(Base):
    __tablename__ = "regions"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)          # e.g. "Kalahandi"
    district = Column(String(120), default="")
    state = Column(String(120), default="Odisha")
    primary_language = Column(String(10), default="or")
    avg_travel_km = Column(Float, default=35.0)         # how far a villager travels to the district hospital
    avg_travel_cost = Column(Float, default=400.0)      # ₹ bus fare + lost daily wage
    avg_travel_hours = Column(Float, default=4.0)


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)
    phone = Column(String(20), unique=True, index=True, nullable=False)   # rural users log in with phone, not email
    email = Column(String(200), nullable=True)
    hashed_password = Column(String(200), nullable=False)
    role = Column(String(40), nullable=False, default="patient")
    preferred_language = Column(String(10), default="hi")
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)


class Hospital(Base):
    __tablename__ = "hospitals"
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=False)
    town = Column(String(120), default="")
    phone = Column(String(20), default="")
    has_emergency = Column(Boolean, default=False)
    sanctioned_doctors = Column(Integer, default=10)    # the PS: "half the sanctioned doctor posts filled"
    doctors_present = Column(Integer, default=5)
