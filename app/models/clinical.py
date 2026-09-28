"""
app/models/clinical.py  –  DOCTORS, AVAILABILITY, APPOINTMENTS, CONSULTATIONS
===============================================================================
Doctor            = a user with role "doctor" + specialty, hospital, languages they speak
AvailabilitySlot  = "Dr Sahu is free 10:00-12:00 tomorrow, can take 8 patients"  ← the hospital
                    staff schedule the PS wants us to integrate with
Appointment       = a patient booked into a slot (or a same-day request). Offline-syncable.
Consultation      = the actual call: mode (video/audio/text picked by bandwidth), room id for the
                    video app, doctor's notes, diagnosis. Ends with a Prescription.
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.core import now
from app.models.patients import SyncMixin


class Doctor(Base):
    __tablename__ = "doctors"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=True)
    specialty = Column(String(60), default="general_medicine")
    qualification = Column(String(120), default="MBBS")
    languages = Column(String(120), default="hi,en")    # comma-separated language codes
    is_online = Column(Boolean, default=False)          # currently reachable for tele-consults
    consultation_fee = Column(Float, default=0.0)       # 0 = free (government)
    total_consultations = Column(Integer, default=0)

    user = relationship("User")
    hospital = relationship("Hospital")


class AvailabilitySlot(Base):
    __tablename__ = "availability_slots"
    id = Column(Integer, primary_key=True)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    capacity = Column(Integer, default=6)
    booked = Column(Integer, default=0)
    modes = Column(String(40), default="video,audio,text")

    doctor = relationship("Doctor")


class Appointment(Base, SyncMixin):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=True)
    slot_id = Column(Integer, ForeignKey("availability_slots.id"), nullable=True)
    triage_id = Column(Integer, ForeignKey("triage_results.id"), nullable=True)
    scheduled_at = Column(DateTime, nullable=True)
    status = Column(String(30), default="requested")    # requested | confirmed | completed | cancelled | no_show
    mode = Column(String(20), default="audio")          # video | audio | text
    reason = Column(Text, default="")
    booked_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=now)

    patient = relationship("Patient")
    doctor = relationship("Doctor")


class Consultation(Base):
    __tablename__ = "consultations"
    id = Column(Integer, primary_key=True)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    doctor_id = Column(Integer, ForeignKey("doctors.id"), nullable=False)
    mode = Column(String(20), default="audio")
    room_id = Column(String(80), default="")            # join code for the video/audio app (WebRTC/Jitsi room)
    status = Column(String(20), default="in_progress")  # in_progress | completed
    started_at = Column(DateTime, default=now)
    ended_at = Column(DateTime, nullable=True)
    notes = Column(Text, default="")
    diagnosis = Column(Text, default="")
    wait_minutes = Column(Integer, default=0)           # booked → started; the PS wants us to measure this
