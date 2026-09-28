"""
app/schemas/__init__.py  –  THE SHAPE OF JSON GOING IN AND OUT
================================================================
Models (app/models/) describe DATABASE tables. Schemas (this file) describe the JSON the API
accepts and returns. Separate on purpose: User has hashed_password, UserOut never shows it.

Naming:  XxxCreate = POST body   ·   XxxUpdate = PATCH body (all optional)   ·   XxxOut = response
Pydantic validates automatically: send age=-3 where Field(ge=0) is set → clear 422 error, our code never runs.
"""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Auth ----------
class UserCreate(BaseModel):
    name: str
    phone: str = Field(min_length=10, max_length=15)
    password: str = Field(min_length=4)               # short PINs are realistic for low-literacy users
    role: str = "patient"
    preferred_language: str = "hi"
    region_id: Optional[int] = None
    email: Optional[str] = None


class UserOut(ORM):
    id: int
    name: str
    phone: str
    role: str
    preferred_language: str
    region_id: Optional[int]
    is_active: bool


class LoginRequest(BaseModel):
    phone_or_email: str
    password: str


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- Core ----------
class RegionOut(ORM):
    id: int
    name: str
    district: str
    state: str
    primary_language: str
    avg_travel_km: float
    avg_travel_cost: float
    avg_travel_hours: float


class RegionCreate(BaseModel):
    name: str
    district: str = ""
    state: str = "Odisha"
    primary_language: str = "or"
    avg_travel_km: float = 35
    avg_travel_cost: float = 400
    avg_travel_hours: float = 4


class HospitalOut(ORM):
    id: int
    name: str
    region_id: int
    town: str
    phone: str
    has_emergency: bool
    sanctioned_doctors: int
    doctors_present: int


# ---------- Patients & records ----------
class PatientCreate(BaseModel):
    name: str
    age: int = Field(ge=0, le=120)
    sex: str = "F"
    phone: str = ""
    village: str = ""
    region_id: Optional[int] = None
    language: str = "or"
    blood_group: str = ""
    allergies: str = ""
    chronic_conditions: str = ""
    is_pregnant: bool = False
    client_id: Optional[str] = None                    # phone app's own UUID (for offline sync)


class PatientOut(ORM):
    id: int
    client_id: Optional[str]
    name: str
    age: int
    sex: str
    phone: str
    village: str
    region_id: Optional[int]
    language: str
    blood_group: str
    allergies: str
    chronic_conditions: str
    is_pregnant: bool
    updated_at: datetime
    version: int


class RecordCreate(BaseModel):
    record_type: str = "visit"
    title: str = ""
    content: str = ""
    temperature_c: Optional[float] = None
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    pulse: Optional[int] = None
    spo2: Optional[int] = None
    weight_kg: Optional[float] = None
    client_id: Optional[str] = None


class RecordOut(ORM):
    id: int
    client_id: Optional[str]
    patient_id: int
    record_type: str
    title: str
    content: str
    temperature_c: Optional[float]
    bp_systolic: Optional[int]
    bp_diastolic: Optional[int]
    pulse: Optional[int]
    spo2: Optional[int]
    weight_kg: Optional[float]
    recorded_by: Optional[int]
    consultation_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    version: int


class PrescriptionItemIn(BaseModel):
    medicine_id: int
    dosage: str = ""
    frequency: str = "1-0-1"
    duration_days: int = 5
    quantity: int = 10
    instructions: str = ""


class PrescriptionItemOut(ORM):
    id: int
    medicine_id: int
    dosage: str
    frequency: str
    duration_days: int
    quantity: int
    instructions: str


class PrescriptionOut(ORM):
    id: int
    patient_id: int
    doctor_id: int
    consultation_id: Optional[int]
    diagnosis: str
    advice: str
    follow_up_days: Optional[int]
    created_at: datetime
    items: list[PrescriptionItemOut]


# ---------- Doctors & appointments ----------
class DoctorOut(ORM):
    id: int
    user_id: int
    hospital_id: Optional[int]
    specialty: str
    qualification: str
    languages: str
    is_online: bool
    consultation_fee: float
    total_consultations: int


class SlotCreate(BaseModel):
    start_time: datetime
    end_time: datetime
    capacity: int = 6
    modes: str = "video,audio,text"


class SlotOut(ORM):
    id: int
    doctor_id: int
    start_time: datetime
    end_time: datetime
    capacity: int
    booked: int
    modes: str


class AppointmentCreate(BaseModel):
    patient_id: int
    doctor_id: Optional[int] = None                    # omit → we pick the best available doctor
    slot_id: Optional[int] = None
    triage_id: Optional[int] = None
    reason: str = ""
    specialty: Optional[str] = None
    network_kbps: Optional[float] = None               # measured by the app → picks video/audio/text
    latency_ms: Optional[float] = None
    client_id: Optional[str] = None


class AppointmentOut(ORM):
    id: int
    client_id: Optional[str]
    patient_id: int
    doctor_id: Optional[int]
    slot_id: Optional[int]
    triage_id: Optional[int]
    scheduled_at: Optional[datetime]
    status: str
    mode: str
    reason: str
    created_at: datetime
    updated_at: datetime
    version: int


class ConsultationStart(BaseModel):
    network_kbps: Optional[float] = None
    latency_ms: Optional[float] = None


class ConsultationComplete(BaseModel):
    notes: str = ""
    diagnosis: str = ""
    advice: str = ""
    follow_up_days: Optional[int] = None
    prescription_items: list[PrescriptionItemIn] = []


class ConsultationOut(ORM):
    id: int
    appointment_id: int
    patient_id: int
    doctor_id: int
    mode: str
    room_id: str
    status: str
    started_at: datetime
    ended_at: Optional[datetime]
    notes: str
    diagnosis: str
    wait_minutes: int


# ---------- Pharmacy ----------
class MedicineOut(ORM):
    id: int
    name: str
    generic_name: str
    name_hi: str
    name_or: str
    form: str
    is_essential: bool
    typical_price: float


class PharmacyOut(ORM):
    id: int
    name: str
    region_id: int
    village: str
    phone: str
    is_government: bool
    open_hours: str


class StockUpdate(BaseModel):
    medicine_id: int
    quantity: int = Field(ge=0)
    price: Optional[float] = None


class ReservationCreate(BaseModel):
    patient_id: int
    medicine_id: int
    quantity: int = Field(gt=0)
    pharmacy_id: Optional[int] = None                  # omit → nearest pharmacy with stock
    prescription_id: Optional[int] = None


class ReservationOut(ORM):
    id: int
    pharmacy_id: int
    medicine_id: int
    patient_id: int
    prescription_id: Optional[int]
    quantity: int
    status: str
    expires_at: Optional[datetime]
    created_at: datetime


# ---------- Triage ----------
class TriageRequest(BaseModel):
    symptoms: str | list[str]                          # "bukhar aur khansi" or ["fever","cough"] – any language
    age: Optional[int] = Field(default=None, ge=0, le=120)
    sex: str = ""
    duration_days: int = Field(default=1, ge=0)
    patient_id: Optional[int] = None
    spo2: Optional[int] = None
    temperature_c: Optional[float] = None
    is_pregnant: bool = False
    language: Optional[str] = None                     # default: caller's preferred language
    client_id: Optional[str] = None                    # if computed offline and synced later
    auto_book: bool = False                            # urgent/routine → also book the best doctor


class TriageOut(ORM):
    id: int
    patient_id: Optional[int]
    symptoms_input: str
    symptoms_normalized: str
    urgency: str
    red_flags: str
    recommended_action: str
    recommended_specialty: str
    language: str
    model_name: str
    computed_offline: bool
    created_at: datetime


# ---------- Sync ----------
class SyncRecord(BaseModel):
    type: str                                          # patient | health_record | triage | appointment
    client_id: str
    updated_at: datetime
    data: dict


class SyncPush(BaseModel):
    device_id: str
    records: list[SyncRecord]


class SyncPull(BaseModel):
    device_id: str
    since: Optional[datetime] = None                   # null = full download
    patient_ids: list[int] = []                        # a health worker's assigned patients
    region_id: Optional[int] = None


# ---------- Misc ----------
class NotificationOut(ORM):
    id: int
    phone: str
    channel: str
    message: str
    language: str
    category: str
    status: str
    is_read: bool
    created_at: datetime


class EventOut(ORM):
    id: int
    source_module: str
    event: str
    detail: str
    created_at: datetime
