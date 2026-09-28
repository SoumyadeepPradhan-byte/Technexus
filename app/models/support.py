"""
app/models/support.py  –  TRIAGE RESULTS, SYNC LOG, NOTIFICATIONS, IMPACT, AUDIT
==================================================================================
TriageResult  = what the AI symptom checker said (kept, so a doctor can see it before the call and
                so we can audit clinical safety)
SyncLog       = every offline push/pull from a device – proves the offline story works
Notification  = SMS-style messages (works on feature phones; the PS says low literacy / no smartphone)
ImpactEvent   = "trip avoided", "wasted trip prevented", "wait minutes" – the PS asks for measurable impact
EventLog      = audit trail of everything the system did automatically (show GET /events to judges)
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text

from app.core.database import Base
from app.models.core import now


class TriageResult(Base):
    __tablename__ = "triage_results"
    id = Column(Integer, primary_key=True)
    client_id = Column(String(64), unique=True, index=True, nullable=True)   # so triage done offline can sync later
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    symptoms_input = Column(Text, default="")           # what the user typed/tapped, any language
    symptoms_normalized = Column(Text, default="")      # canonical codes: "fever,cough"
    age = Column(Integer, nullable=True)
    sex = Column(String(10), default="")
    duration_days = Column(Integer, default=1)
    urgency = Column(String(20), nullable=False)        # emergency | urgent | routine | self_care
    red_flags = Column(Text, default="")
    recommended_action = Column(Text, default="")
    recommended_specialty = Column(String(60), default="general_medicine")
    advice_localized = Column(Text, default="")
    language = Column(String(10), default="hi")
    model_name = Column(String(60), default="rules_v0")
    computed_offline = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class SyncLog(Base):
    __tablename__ = "sync_log"
    id = Column(Integer, primary_key=True)
    device_id = Column(String(80), default="")
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    direction = Column(String(10), nullable=False)      # push | pull
    records = Column(Integer, default=0)
    conflicts = Column(Integer, default=0)
    bytes_out = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)


class Notification(Base):
    __tablename__ = "notifications"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    phone = Column(String(20), default="")
    channel = Column(String(10), default="sms")         # sms | app | ivr (voice call for non-readers)
    message = Column(Text, nullable=False)
    language = Column(String(10), default="hi")
    category = Column(String(30), default="info")       # appointment | medicine | triage | reminder
    status = Column(String(20), default="queued")       # queued | sent  (a real SMS gateway would flip this)
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)


class ImpactEvent(Base):
    __tablename__ = "impact_events"
    id = Column(Integer, primary_key=True)
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=True)
    event_type = Column(String(40), nullable=False)     # trip_avoided | wasted_trip_prevented | remote_consultation | wait_minutes | emergency_escalated
    value = Column(Float, default=1.0)                  # km saved, ₹ saved, minutes...
    detail = Column(String(200), default="")
    created_at = Column(DateTime, default=now)


class EventLog(Base):
    __tablename__ = "event_log"
    id = Column(Integer, primary_key=True)
    source_module = Column(String(40), nullable=False)
    event = Column(String(160), nullable=False)
    detail = Column(Text, default="")
    created_at = Column(DateTime, default=now)
