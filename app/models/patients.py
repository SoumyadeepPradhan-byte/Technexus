"""
app/models/patients.py  –  PATIENTS, HEALTH RECORDS, PRESCRIPTIONS  (offline-capable)
======================================================================================
Every table here has four extra columns that make OFFLINE SYNC possible:
    client_id   – a UUID the phone app generates itself, so a record created with no signal
                  still has a stable identity before the server ever sees it
    updated_at  – used for "last write wins" when the same record was edited in two places
    version     – increases on every save; lets the app detect stale copies
    is_deleted  – we never physically delete (a deleted row must still sync to other devices)

Patient       = the person (village, language, allergies, chronic conditions)
HealthRecord  = one entry in their file: a visit note, vitals, diagnosis, lab result
Prescription  = written by a doctor after a consultation; PrescriptionItem = one medicine line
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.core import now


class SyncMixin:
    client_id = Column(String(64), unique=True, index=True, nullable=True)
    updated_at = Column(DateTime, default=now, onupdate=now)
    version = Column(Integer, default=1)
    is_deleted = Column(Boolean, default=False)


class Patient(Base, SyncMixin):
    __tablename__ = "patients"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)   # null = registered by a health worker on their behalf
    name = Column(String(120), nullable=False)
    age = Column(Integer, nullable=False)
    sex = Column(String(10), default="F")               # F | M | O
    phone = Column(String(20), default="")
    village = Column(String(120), default="")
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=True)
    language = Column(String(10), default="or")
    blood_group = Column(String(5), default="")
    allergies = Column(Text, default="")
    chronic_conditions = Column(Text, default="")       # e.g. "diabetes, hypertension"
    is_pregnant = Column(Boolean, default=False)
    registered_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    records = relationship("HealthRecord", back_populates="patient")


class HealthRecord(Base, SyncMixin):
    __tablename__ = "health_records"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    record_type = Column(String(30), default="visit")   # visit | vitals | diagnosis | lab | note
    title = Column(String(160), default="")
    content = Column(Text, default="")
    # vitals (optional) – stored as columns so they're tiny to sync
    temperature_c = Column(Float, nullable=True)
    bp_systolic = Column(Integer, nullable=True)
    bp_diastolic = Column(Integer, nullable=True)
    pulse = Column(Integer, nullable=True)
    spo2 = Column(Integer, nullable=True)
    weight_kg = Column(Float, nullable=True)
    recorded_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    patient = relationship("Patient", back_populates="records")


class Prescription(Base, SyncMixin):
    __tablename__ = "prescriptions"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    consultation_id = Column(Integer, ForeignKey("consultations.id"), nullable=True)
    diagnosis = Column(Text, default="")
    advice = Column(Text, default="")
    follow_up_days = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=now)

    items = relationship("PrescriptionItem", back_populates="prescription", cascade="all, delete-orphan")


class PrescriptionItem(Base):
    __tablename__ = "prescription_items"
    id = Column(Integer, primary_key=True)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    dosage = Column(String(60), default="")             # "500 mg"
    frequency = Column(String(60), default="")          # "1-0-1" (morning-noon-night, how villagers read it)
    duration_days = Column(Integer, default=5)
    quantity = Column(Integer, default=10)
    instructions = Column(String(200), default="")      # "after food"

    prescription = relationship("Prescription", back_populates="items")
