"""
app/services/integration.py  –  THE HEART OF THE PROJECT
==========================================================
This is where the modules TALK TO EACH OTHER. Routers are thin; the real logic is here.
If you understand this one file, you understand the whole backend.

The patient journey the judges will watch (each step writes to EventLog → GET /events):

  TRIAGE → DOCTOR MATCHING → APPOINTMENT
    run_triage():           symptoms in any language → AI urgency. Emergency → escalate_emergency()
                            (nearest emergency hospital, SMS, impact event). Otherwise, if auto_book,
                            → book_appointment() with the best doctor for that specialty + language.
  BANDWIDTH → CONSULTATION MODE
    book_appointment():     network measurement → video / audio / text. Confirms via SMS in the
                            patient's language. Records "trip avoided" impact.
  CONSULTATION → PRESCRIPTION → PHARMACY → RESERVATION
    complete_consultation(): doctor's notes become a HealthRecord + Prescription. For every medicine we
                            check nearby pharmacies' live stock → reserve it → SMS the patient where to
                            collect. No stock anywhere → SMS "don't travel yet" (wasted trip prevented).
  OFFLINE DEVICES ↔ SERVER
    sync_push():            records created with no signal come in with client_ids; newer wins, conflicts
                            are returned, never silently overwritten.
    sync_pull():            only what changed since the device last synced → tiny payloads.

Rule of thumb: if module A needs to change something in module B, write a function HERE,
call log_event(), and call it from the router.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.ai.bandwidth import recommend_mode
from app.ai.language import translate
from app.ai.matching import rank_doctors
from app.ai.triage import assess_symptoms
from app.core.config import settings
from app.models import (Appointment, AvailabilitySlot, Consultation, Doctor, EventLog, HealthRecord, Hospital,
                        ImpactEvent, Medicine, MedicineReservation, Notification, Patient, Pharmacy, PharmacyStock,
                        Prescription, PrescriptionItem, Region, SyncLog, TriageResult, User)


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def log_event(db: Session, module: str, event: str, detail: str = ""):
    db.add(EventLog(source_module=module, event=event, detail=detail))


def notify(db: Session, phone: str, message: str, language: str = "hi", category: str = "info",
           user_id: int | None = None, channel: str = "sms"):
    """Queue an SMS/IVR-style message. A real SMS gateway (MSG91, Twilio) would send `message` to `phone`."""
    db.add(Notification(user_id=user_id, phone=phone, channel=channel, message=message, language=language,
                        category=category))


def record_impact(db: Session, region_id: int | None, event_type: str, value: float = 1.0, detail: str = "",
                  patient_id: int | None = None):
    db.add(ImpactEvent(region_id=region_id, patient_id=patient_id, event_type=event_type, value=value, detail=detail))


# ---------------------------------------------------------------- Triage
def run_triage(db: Session, data: dict, caller: User | None) -> tuple[TriageResult, dict, Appointment | None]:
    """Runs the AI symptom checker, stores the result, escalates emergencies, optionally books a doctor."""
    patient = db.get(Patient, data["patient_id"]) if data.get("patient_id") else None
    lang = data.get("language") or (patient.language if patient else None) or (caller.preferred_language if caller else settings.DEFAULT_LANGUAGE)
    age = data.get("age") if data.get("age") is not None else (patient.age if patient else None)
    vitals = {k: data.get(k) for k in ("spo2", "temperature_c") if data.get(k) is not None}
    result = assess_symptoms(data["symptoms"], age=age, sex=data.get("sex") or (patient.sex if patient else ""),
                             duration_days=data.get("duration_days", 1), vitals=vitals,
                             is_pregnant=data.get("is_pregnant") or (patient.is_pregnant if patient else False),
                             language=lang, emergency_number=settings.EMERGENCY_NUMBER)

    tr = TriageResult(client_id=data.get("client_id") or None, patient_id=patient.id if patient else None,
                      symptoms_input=data["symptoms"] if isinstance(data["symptoms"], str) else ", ".join(data["symptoms"]),
                      symptoms_normalized=",".join(result["symptoms_normalized"]), age=age, sex=data.get("sex", ""),
                      duration_days=data.get("duration_days", 1), urgency=result["urgency"],
                      red_flags="; ".join(result["red_flags"]), recommended_action=result["recommended_action"],
                      recommended_specialty=result["recommended_specialty"], advice_localized=result["recommended_action"],
                      language=lang, model_name=result["model_name"], computed_offline=bool(data.get("client_id")))
    db.add(tr)
    db.flush()
    log_event(db, "triage", f"triage #{tr.id}: {result['urgency']}",
              f"symptoms={tr.symptoms_normalized or 'unrecognized'}; specialty={result['recommended_specialty']}")

    appointment = None
    if result["escalation"]:
        escalate_emergency(db, tr, patient, lang)
    elif data.get("auto_book") and patient and result["urgency"] in ("urgent", "routine"):
        appointment = book_appointment(db, patient, specialty=result["recommended_specialty"], triage_id=tr.id,
                                       reason=tr.symptoms_input, network_kbps=data.get("network_kbps"),
                                       latency_ms=data.get("latency_ms"), booked_by=caller,
                                       urgency=result["urgency"])
    db.commit()
    db.refresh(tr)
    return tr, result, appointment


def escalate_emergency(db: Session, tr: TriageResult, patient: Patient | None, lang: str):
    """Clear escalation path: find the nearest hospital WITH emergency care, alert everyone."""
    region_id = patient.region_id if patient else None
    hosp = (db.query(Hospital).filter(Hospital.has_emergency.is_(True), Hospital.region_id == region_id).first()
            or db.query(Hospital).filter(Hospital.has_emergency.is_(True)).first())
    name = patient.name if patient else "patient"
    msg = translate("emergency_escalated", lang, patient=name, hospital=hosp.name if hosp else "district hospital",
                    phone=hosp.phone if hosp else settings.EMERGENCY_NUMBER)
    if patient and patient.phone:
        notify(db, patient.phone, tr.recommended_action, lang, "triage", channel="ivr")   # voice call, not just text
    if hosp and hosp.phone:
        notify(db, hosp.phone, msg, "en", "triage")
    record_impact(db, region_id, "emergency_escalated", 1, f"triage #{tr.id}", patient.id if patient else None)
    log_event(db, "triage", f"EMERGENCY escalated for {name}", f"→ {hosp.name if hosp else 'no hospital on file'}; red flags: {tr.red_flags}")


# ---------------------------------------------------------------- Doctors & appointments
def doctor_candidates(db: Session, specialty: str, language: str, region_id: int | None, urgency: str) -> list[dict]:
    now = utcnow()
    rows = []
    for d in db.query(Doctor).join(User).filter(User.is_active.is_(True)).all():
        free = (db.query(func.coalesce(func.sum(AvailabilitySlot.capacity - AvailabilitySlot.booked), 0))
                .filter(AvailabilitySlot.doctor_id == d.id, AvailabilitySlot.end_time > now).scalar())
        rows.append({"id": d.id, "name": d.user.name, "specialty": d.specialty, "languages": d.languages.split(","),
                     "is_online": d.is_online, "region_id": d.hospital.region_id if d.hospital else None,
                     "open_capacity": int(free), "total_consultations": d.total_consultations,
                     "hospital": d.hospital.name if d.hospital else ""})
    return rank_doctors(rows, specialty, language, region_id, urgency)


def book_appointment(db: Session, patient: Patient, specialty: str | None = None, doctor_id: int | None = None,
                     slot_id: int | None = None, triage_id: int | None = None, reason: str = "",
                     network_kbps: float | None = None, latency_ms: float | None = None, booked_by: User | None = None,
                     urgency: str = "routine", client_id: str | None = None) -> Appointment:
    """Pick doctor (if not given) → pick earliest free slot → pick mode by bandwidth → confirm by SMS."""
    if doctor_id is None:
        ranked = doctor_candidates(db, specialty or "general_medicine", patient.language, patient.region_id, urgency)
        ranked = [r for r in ranked if r["open_capacity"] > 0]
        if not ranked:
            raise ValueError("No doctor with free slots right now")
        doctor_id = ranked[0]["id"]
    doctor = db.get(Doctor, doctor_id)

    slot = db.get(AvailabilitySlot, slot_id) if slot_id else (
        db.query(AvailabilitySlot).filter(AvailabilitySlot.doctor_id == doctor_id, AvailabilitySlot.end_time > utcnow(),
                                          AvailabilitySlot.booked < AvailabilitySlot.capacity)
        .order_by(AvailabilitySlot.start_time).first())
    if slot is None or slot.booked >= slot.capacity:
        raise ValueError("Selected slot is full")
    slot.booked += 1

    mode = recommend_mode(network_kbps, latency_ms, low_bandwidth_kbps=settings.LOW_BANDWIDTH_KBPS)
    chosen_mode = mode["mode"] if mode["mode"] in slot.modes.split(",") else slot.modes.split(",")[-1]

    ap = Appointment(client_id=client_id, patient_id=patient.id, doctor_id=doctor_id, slot_id=slot.id, triage_id=triage_id,
                     scheduled_at=slot.start_time, status="confirmed", mode=chosen_mode, reason=reason,
                     booked_by=booked_by.id if booked_by else None)
    db.add(ap)
    db.flush()

    region = db.get(Region, patient.region_id) if patient.region_id else None
    if patient.phone:
        notify(db, patient.phone, translate("appointment_confirmed", patient.language, doctor=doctor.user.name,
                                            time=slot.start_time.strftime("%d %b %H:%M"), mode=chosen_mode),
               patient.language, "appointment")
    record_impact(db, patient.region_id, "trip_avoided", region.avg_travel_km if region else 30,
                  f"appointment #{ap.id} by {chosen_mode}", patient.id)
    record_impact(db, patient.region_id, "money_saved", region.avg_travel_cost if region else 300,
                  f"appointment #{ap.id}", patient.id)
    log_event(db, "appointments", f"appointment #{ap.id} booked: {patient.name} → Dr {doctor.user.name}",
              f"{doctor.specialty}, {chosen_mode} ({mode['reason']}), slot {slot.start_time:%d %b %H:%M}")
    db.commit()
    db.refresh(ap)
    return ap


def start_consultation(db: Session, ap: Appointment, network_kbps: float | None, latency_ms: float | None) -> Consultation:
    mode = recommend_mode(network_kbps, latency_ms, low_bandwidth_kbps=settings.LOW_BANDWIDTH_KBPS)["mode"] if network_kbps is not None else ap.mode
    c = Consultation(appointment_id=ap.id, patient_id=ap.patient_id, doctor_id=ap.doctor_id, mode=mode,
                     room_id=f"thb-{uuid.uuid4().hex[:8]}",
                     wait_minutes=max(0, int((utcnow() - ap.created_at).total_seconds() // 60)))
    ap.status = "in_progress"
    db.add(c)
    db.flush()
    record_impact(db, ap.patient.region_id, "wait_minutes", c.wait_minutes, f"consultation #{c.id}", ap.patient_id)
    log_event(db, "consultations", f"consultation #{c.id} started ({mode})", f"room {c.room_id}")
    db.commit()
    db.refresh(c)
    return c


def complete_consultation(db: Session, c: Consultation, data: dict, doctor_user: User) -> dict:
    """Doctor finishes: notes → health record; prescription → check pharmacy stock → reserve → SMS."""
    c.status, c.ended_at, c.notes, c.diagnosis = "completed", utcnow(), data.get("notes", ""), data.get("diagnosis", "")
    ap = db.get(Appointment, c.appointment_id)
    ap.status = "completed"
    patient = db.get(Patient, c.patient_id)
    doctor = db.get(Doctor, c.doctor_id)
    doctor.total_consultations += 1

    db.add(HealthRecord(patient_id=patient.id, record_type="visit", title=f"Tele-consultation with Dr {doctor.user.name}",
                        content=f"Diagnosis: {c.diagnosis}\nNotes: {c.notes}", recorded_by=doctor_user.id, consultation_id=c.id))
    record_impact(db, patient.region_id, "remote_consultation", 1, f"consultation #{c.id}", patient.id)

    prescription, reservations, unavailable = None, [], []
    if data.get("prescription_items"):
        prescription = Prescription(patient_id=patient.id, doctor_id=doctor.id, consultation_id=c.id,
                                    diagnosis=c.diagnosis, advice=data.get("advice", ""), follow_up_days=data.get("follow_up_days"))
        db.add(prescription)
        db.flush()
        for it in data["prescription_items"]:
            db.add(PrescriptionItem(prescription_id=prescription.id, **it))
            res = reserve_medicine(db, patient, it["medicine_id"], it["quantity"], prescription.id)
            (reservations if res else unavailable).append(res or it["medicine_id"])
    log_event(db, "consultations", f"consultation #{c.id} completed",
              f"{len(reservations)} medicines reserved, {len(unavailable)} unavailable nearby")
    db.commit()
    db.refresh(c)
    return {"consultation": c, "prescription": prescription, "reservations": reservations,
            "unavailable_medicine_ids": unavailable}


# ---------------------------------------------------------------- Pharmacy
def find_stock(db: Session, medicine_id: int, region_id: int | None, quantity: int = 1) -> list[PharmacyStock]:
    """Pharmacies in the patient's district that have enough of the medicine, government ones first."""
    q = db.query(PharmacyStock).join(Pharmacy).filter(PharmacyStock.medicine_id == medicine_id,
                                                        PharmacyStock.quantity >= quantity)
    if region_id:
        q = q.filter(Pharmacy.region_id == region_id)
    return q.order_by(Pharmacy.is_government.desc(), PharmacyStock.price).all()


def reserve_medicine(db: Session, patient: Patient, medicine_id: int, quantity: int,
                     prescription_id: int | None = None, pharmacy_id: int | None = None) -> MedicineReservation | None:
    med = db.get(Medicine, medicine_id)
    stocks = find_stock(db, medicine_id, patient.region_id, quantity)
    if pharmacy_id:
        stocks = [s for s in stocks if s.pharmacy_id == pharmacy_id]
    med_name = {"hi": med.name_hi, "or": med.name_or}.get(patient.language) or med.name
    if not stocks:
        if patient.phone:
            notify(db, patient.phone, translate("medicine_unavailable", patient.language, medicine=med_name),
                   patient.language, "medicine")
        record_impact(db, patient.region_id, "wasted_trip_prevented", 1, f"{med.name} not in stock", patient.id)
        log_event(db, "pharmacy", f"{med.name} unavailable in region for {patient.name}", "patient told not to travel")
        return None
    s = stocks[0]
    s.quantity -= quantity
    r = MedicineReservation(pharmacy_id=s.pharmacy_id, medicine_id=medicine_id, patient_id=patient.id,
                            prescription_id=prescription_id, quantity=quantity,
                            expires_at=utcnow() + timedelta(hours=settings.RESERVATION_HOURS))
    db.add(r)
    db.flush()
    if patient.phone:
        notify(db, patient.phone, translate("medicine_reserved", patient.language, medicine=med_name, pharmacy=s.pharmacy.name,
                                            village=s.pharmacy.village, until=r.expires_at.strftime("%d %b %H:%M"), id=r.id),
               patient.language, "medicine")
    record_impact(db, patient.region_id, "wasted_trip_prevented", 1, f"{med.name} reserved at {s.pharmacy.name}", patient.id)
    log_event(db, "pharmacy", f"{med.name} x{quantity} reserved at {s.pharmacy.name} for {patient.name}",
              f"reservation #{r.id}, {s.quantity} left in stock")
    return r


# ---------------------------------------------------------------- Offline sync
SYNC_TYPES = {
    "patient": (Patient, {"name", "age", "sex", "phone", "village", "region_id", "language", "blood_group", "allergies",
                          "chronic_conditions", "is_pregnant"}),
    "health_record": (HealthRecord, {"patient_id", "record_type", "title", "content", "temperature_c", "bp_systolic",
                                     "bp_diastolic", "pulse", "spo2", "weight_kg"}),
    "appointment": (Appointment, {"patient_id", "doctor_id", "reason", "mode", "status"}),
}


def _resolve_patient_ref(db: Session, data: dict) -> dict:
    """Records created offline reference the patient by the patient's client_id. Translate to a server id."""
    ref = data.pop("patient_client_id", None)
    if ref and not data.get("patient_id"):
        p = db.query(Patient).filter_by(client_id=ref).first()
        if p:
            data["patient_id"] = p.id
    return data


def sync_push(db: Session, device_id: str, records: list[dict], user: User) -> dict:
    """Upsert by client_id. Newer updated_at wins; older incoming = conflict returned (never silently lost)."""
    accepted, conflicts, mapping = 0, [], {}
    triage_results = []
    for rec in sorted(records, key=lambda r: 0 if r["type"] == "patient" else 1):   # patients first
        rtype, cid, data = rec["type"], rec["client_id"], dict(rec["data"])
        incoming_ts = rec["updated_at"].replace(tzinfo=None)

        if rtype == "triage":
            existing = db.query(TriageResult).filter_by(client_id=cid).first()
            if existing:
                mapping[cid] = existing.id
                continue
            data = _resolve_patient_ref(db, data)
            tr, _, _ = run_triage(db, {**data, "client_id": cid}, user)
            mapping[cid] = tr.id
            triage_results.append(tr.urgency)
            accepted += 1
            continue

        if rtype not in SYNC_TYPES:
            conflicts.append({"client_id": cid, "reason": f"unknown type {rtype}"})
            continue
        model, allowed = SYNC_TYPES[rtype]
        data = _resolve_patient_ref(db, data)
        clean = {k: v for k, v in data.items() if k in allowed}
        existing = db.query(model).filter_by(client_id=cid).first()
        if existing is None:
            obj = model(client_id=cid, **clean)
            if rtype == "patient":
                obj.registered_by = user.id
            if rtype == "health_record":
                obj.recorded_by = user.id
            db.add(obj)
            db.flush()
            accepted += 1
        elif incoming_ts > existing.updated_at:
            for k, v in clean.items():
                setattr(existing, k, v)
            existing.version += 1
            obj = existing
            accepted += 1
        else:
            conflicts.append({"client_id": cid, "reason": "server copy is newer", "server_version": existing.version,
                              "server_updated_at": existing.updated_at})
            obj = existing
        mapping[cid] = obj.id

    db.add(SyncLog(device_id=device_id, user_id=user.id, direction="push", records=len(records), conflicts=len(conflicts)))
    log_event(db, "sync", f"push from {device_id}: {accepted} accepted, {len(conflicts)} conflicts",
              f"triage urgencies: {triage_results}" if triage_results else "")
    db.commit()
    return {"accepted": accepted, "conflicts": conflicts, "server_ids": mapping, "server_time": utcnow()}


def sync_pull(db: Session, device_id: str, since: datetime | None, patient_ids: list[int], region_id: int | None,
              user: User) -> dict:
    """Everything the device needs, but ONLY what changed since `since`. Small on purpose."""
    def changed(q, model):
        return q.filter(model.updated_at > since).all() if since else q.all()

    pq = db.query(Patient)
    if patient_ids:
        pq = pq.filter(Patient.id.in_(patient_ids))
    elif region_id:
        pq = pq.filter(Patient.region_id == region_id)
    patients = changed(pq, Patient)
    pids = patient_ids or [p.id for p in patients]
    records = changed(db.query(HealthRecord).filter(HealthRecord.patient_id.in_(pids)), HealthRecord) if pids else []
    prescriptions = changed(db.query(Prescription).filter(Prescription.patient_id.in_(pids)), Prescription) if pids else []
    appointments = changed(db.query(Appointment).filter(Appointment.patient_id.in_(pids)), Appointment) if pids else []
    # the essentials list + which nearby pharmacies stock them: lets the app answer "is it available?" offline
    stock = db.query(PharmacyStock).join(Pharmacy)
    if region_id:
        stock = stock.filter(Pharmacy.region_id == region_id)
    stock = stock.filter(PharmacyStock.updated_at > since).all() if since else stock.all()

    payload = {
        "server_time": utcnow(),
        "patients": patients, "health_records": records, "prescriptions": prescriptions, "appointments": appointments,
        "medicine_stock": [{"pharmacy_id": s.pharmacy_id, "medicine_id": s.medicine_id, "quantity": s.quantity,
                            "price": s.price, "updated_at": s.updated_at} for s in stock],
    }
    n = len(patients) + len(records) + len(prescriptions) + len(appointments) + len(stock)
    db.add(SyncLog(device_id=device_id, user_id=user.id, direction="pull", records=n))
    log_event(db, "sync", f"pull to {device_id}: {n} records" + (f" since {since:%d %b %H:%M}" if since else " (full)"))
    db.commit()
    return payload
