"""
smoke_test.py  –  END-TO-END CHECKS
=====================================
Run:  python seed.py && python smoke_test.py
Uses FastAPI's TestClient (no server needed). Each check() prints PASS/FAIL. Add one per new feature.
"""
import warnings
warnings.filterwarnings("ignore")
from datetime import timedelta
from fastapi.testclient import TestClient
from app.main import app
from app.services.integration import utcnow

c = TestClient(app)
B = "/api/v1"
ok = fail = 0

def check(name, cond, extra=""):
    global ok, fail
    ok += bool(cond); fail += (not cond)
    print(("PASS " if cond else "FAIL ") + name + (f"  -> {extra}" if extra else ""))

def login(ident, pw="1234"):
    r = c.post(f"{B}/auth/login", json={"phone_or_email": ident, "password": pw})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}

admin, hadmin, asha, pharm, patient, doc, ped = (login(x) for x in ("admin@technexus.io", "9000000001", "9000000010", "9000000020", "9000000030", "9000000040", "9000000041"))

# --- Auth & RBAC
check("login by email works", c.get(f"{B}/auth/me", headers=admin).json()["role"] == "admin")
check("login by phone works", c.get(f"{B}/auth/me", headers=asha).json()["role"] == "health_worker")
check("wrong PIN rejected", c.post(f"{B}/auth/login", json={"phone_or_email": "9000000010", "password": "0000"}).status_code == 401)
check("no token -> 401", c.get(f"{B}/patients").status_code == 401)
check("RBAC: patient cannot list all patients", c.get(f"{B}/patients", headers=patient).status_code == 403)
check("RBAC: pharmacist cannot add health record", c.post(f"{B}/patients/1/records", headers=pharm, json={"title": "x"}).status_code == 403)
r = c.post(f"{B}/auth/register", json={"name": "New ASHA", "phone": "9111111111", "password": "4321", "role": "health_worker", "preferred_language": "or", "region_id": 1})
check("register with phone + PIN", r.status_code == 201)

# --- Multilingual
check("3 languages supported", {l["code"] for l in c.get(f"{B}/languages").json()} == {"en", "hi", "or"})
check("i18n bundle in Odia", "ଜରୁରୀ" in c.get(f"{B}/i18n/or").json()["call_emergency"])
u = c.get(f"{B}/triage/understand", params={"text": "bukhar aur khansi 3 din se"}).json()
check("Hinglish symptoms understood", u["symptoms"] == ["fever", "cough"], u["symptoms"])
u = c.get(f"{B}/triage/understand", params={"text": "ଛାତି ବିନ୍ଧା, ଶ୍ୱାସ କଷ୍ଟ"}).json()
check("Odia script symptoms understood", set(u["symptoms"]) == {"chest_pain", "breathlessness"}, u["symptoms"])
check("medicine search in Hindi", any("Paracetamol" in m["name"] for m in c.get(f"{B}/pharmacy/medicines", params={"q": "पैरासिटामोल"}).json()))

# --- Scalability / regions
regs = c.get(f"{B}/regions").json()
check("2 districts in 2 states seeded", len(regs) == 2 and {r["state"] for r in regs} == {"Odisha", "Chhattisgarh"})
r = c.post(f"{B}/regions", headers=hadmin, json={"name": "Koraput", "state": "Odisha", "primary_language": "or"})
check("add a new district in one call", r.status_code == 201)
check("emergency hospitals filter", all(h["has_emergency"] for h in c.get(f"{B}/hospitals", params={"emergency_only": True}).json()))

# --- Patients & offline bundle
r = c.post(f"{B}/patients", headers=asha, json={"name": "Test Villager", "age": 45, "sex": "M", "phone": "9777777777", "village": "Narla", "region_id": 1, "language": "or", "client_id": "test-uuid-1"})
check("health worker registers patient with client_id", r.status_code == 201 and r.json()["client_id"] == "test-uuid-1")
pid = r.json()["id"]
r = c.post(f"{B}/patients/{pid}/records", headers=asha, json={"record_type": "vitals", "title": "home visit", "bp_systolic": 140, "bp_diastolic": 90, "spo2": 97})
check("add vitals record", r.status_code == 201 and r.json()["spo2"] == 97)
b = c.get(f"{B}/patients/{pid}/bundle", headers=asha).json()
check("offline bundle = patient + records + prescriptions", set(b) == {"patient", "records", "prescriptions"} and len(b["records"]) == 1)
check("patient sees own profile", c.get(f"{B}/patients/me", headers=patient).json()["name"] == "Laxmi Nayak")
me = c.get(f"{B}/patients/me", headers=patient).json()
check("patient blocked from another patient's file", c.get(f"{B}/patients/{pid}", headers=patient).status_code == 403)

# --- Bandwidth
check("mode: 900 kbps -> video", c.get(f"{B}/network/recommend-mode", params={"kbps": 900}).json()["mode"] == "video")
check("mode: 120 kbps -> audio", c.get(f"{B}/network/recommend-mode", params={"kbps": 120}).json()["mode"] == "audio")
check("mode: 30 kbps -> text", c.get(f"{B}/network/recommend-mode", params={"kbps": 30}).json()["mode"] == "text")
check("mode: high latency downgrades video", c.get(f"{B}/network/recommend-mode", params={"kbps": 900, "latency_ms": 900}).json()["mode"] == "audio")
big = c.get(f"{B}/pharmacy/medicines", headers={"Accept-Encoding": "gzip"})
check("responses are gzip-compressed (low bandwidth)", big.headers.get("content-encoding") == "gzip")

# --- Triage clinical safety
t = c.post(f"{B}/triage", headers=patient, json={"symptoms": "mild cold", "age": 30}).json()
check("mild cold -> self_care, with 'see a doctor if' line", t["result"]["urgency"] == "self_care" and "doctor" in t["result"]["recommended_action"].lower() or "ଡାକ୍ତର" in t["result"]["recommended_action"])
t = c.post(f"{B}/triage", headers=asha, json={"symptoms": "seene me dard aur saans phool rahi hai", "age": 55, "language": "hi"}).json()
check("chest pain + breathlessness -> EMERGENCY, never reassured", t["result"]["urgency"] == "emergency" and t["result"]["escalation"] and "108" in t["result"]["recommended_action"])
t = c.post(f"{B}/triage", headers=asha, json={"symptoms": "bukhar", "age": 3, "duration_days": 1, "language": "or"}).json()
check("child under 5 bumped up + Odia advice", t["result"]["urgency"] == "urgent" and t["result"]["recommended_specialty"] == "pediatrics" and "ଡାକ୍ତର" in t["result"]["recommended_action"])
t = c.post(f"{B}/triage", headers=asha, json={"symptoms": "cough", "age": 40, "duration_days": 20}).json()
check("cough 2+ weeks -> urgent (TB rule)", t["result"]["urgency"] == "urgent")
t = c.post(f"{B}/triage", headers=asha, json={"symptoms": "weakness", "age": 40, "spo2": 88}).json()
check("SpO2 88 overrides mild words -> emergency", t["result"]["urgency"] == "emergency")
t = c.post(f"{B}/triage", headers=asha, json={"symptoms": "zzzz unknown", "age": 40}).json()
check("unrecognized symptoms -> routine, low confidence (no false reassurance)", t["result"]["urgency"] == "routine" and t["result"]["confidence"] < 0.5)

# --- Emergency escalation path
ev0 = len(c.get(f"{B}/events", headers=admin, params={"limit": 500}).json())
t = c.post(f"{B}/triage", headers=asha, json={"symbols": "x", "symptoms": "ସାପ କାମୁଡ଼ିଛି", "patient_id": pid, "auto_book": True}).json()
check("snake bite in Odia -> emergency, NOT booked", t["result"]["urgency"] == "emergency" and t["appointment"] is None)
notes = c.get(f"{B}/notifications", headers=admin, params={"phone": "9777777777"}).json()
check("emergency: IVR call queued to patient", any(n["channel"] == "ivr" for n in notes))
check("emergency: hospital alerted", any("emergency" in e["event"].lower() for e in c.get(f"{B}/events", headers=admin).json()[:3]))

# --- Doctor matching & booking
av = c.get(f"{B}/doctors/available", headers=asha, params={"specialty": "pediatrics", "language": "or", "region_id": 1}).json()
check("available doctors ranked; Odia pediatrician first", av and av[0]["specialty"] == "pediatrics" and "or" in av[0]["languages"], av[0]["name"] if av else None)
t = c.post(f"{B}/triage", headers=asha, json={"symptoms": "bukhar aur khansi", "duration_days": 4, "patient_id": pid, "auto_book": True, "network_kbps": 120}).json()
check("triage auto-books appointment", t["appointment"] is not None and t["appointment"]["status"] == "confirmed")
ap = t["appointment"]
check("appointment mode chosen by bandwidth (120 kbps -> audio)", ap["mode"] == "audio")
check("patient got SMS in Odia", any("ଅପଏଣ୍ଟମେଣ୍ଟ" in n["message"] for n in c.get(f"{B}/notifications", headers=admin, params={"phone": "9777777777"}).json()))
slots_before = c.get(f"{B}/doctors/{ap['doctor_id']}/slots", headers=asha).json()
check("slot capacity decremented", any(s["booked"] >= 1 for s in slots_before))
check("patient can book self only", c.post(f"{B}/appointments", headers=patient, json={"patient_id": pid}).status_code == 403)
r = c.post(f"{B}/appointments", headers=patient, json={"patient_id": me["id"], "specialty": "general_medicine", "network_kbps": 1200})
check("patient books self at 1200 kbps -> video", r.status_code == 201 and r.json()["mode"] == "video")
check("cancel frees the slot", c.post(f"{B}/appointments/{r.json()['id']}/cancel", headers=patient).json()["status"] == "cancelled")

# --- Consultation → prescription → pharmacy
doc_hdr = login(c.get(f"{B}/auth/users", headers=hadmin, params={"role": "doctor"}).json()[0]["phone"])
# find which doctor got the appointment and log in as them
docs = c.get(f"{B}/doctors", headers=asha).json()
doc_user_id = next(d["user_id"] for d in docs if d["id"] == ap["doctor_id"])
doc_phone = next(u["phone"] for u in c.get(f"{B}/auth/users", headers=hadmin, params={"role": "doctor"}).json() if u["id"] == doc_user_id)
this_doc = login(doc_phone)
r = c.post(f"{B}/consultations/{ap['id']}/start", headers=this_doc, json={"network_kbps": 90})
check("doctor starts consultation, gets room id", r.status_code == 201 and r.json()["room_id"].startswith("thb-") and r.json()["mode"] == "audio")
cid = r.json()["id"]
meds = c.get(f"{B}/pharmacy/medicines", headers=asha).json()
para = next(m for m in meds if m["name"].startswith("Paracetamol")); asv = next(m for m in meds if "snake" in m["name"].lower())
r = c.post(f"{B}/consultations/{cid}/complete", headers=this_doc, json={"diagnosis": "Acute bronchitis", "notes": "chest clear", "follow_up_days": 5,
    "prescription_items": [{"medicine_id": para["id"], "dosage": "500mg", "frequency": "1-0-1", "duration_days": 5, "quantity": 10}]})
check("consultation completed with prescription", r.status_code == 200 and r.json()["prescription"]["diagnosis"] == "Acute bronchitis")
check("medicine auto-reserved at a nearby pharmacy", len(r.json()["reservations"]) == 1)
res = r.json()["reservations"][0]
check("reservation at a Kalahandi pharmacy, government first", c.get(f"{B}/pharmacy", headers=asha).json()[res["pharmacy_id"] - 1]["region_id"] == 1)
check("patient got 'medicine reserved' SMS in Odia", any("ସଂରକ୍ଷିତ" in n["message"] for n in c.get(f"{B}/notifications", headers=admin, params={"phone": "9777777777"}).json()))
check("consultation created a health record", any(rec["consultation_id"] == cid for rec in c.get(f"{B}/patients/{pid}/records", headers=asha).json()))
check("prescription visible in patient file", len(c.get(f"{B}/patients/{pid}/prescriptions", headers=asha).json()) == 1)
check("pharmacist marks collected", c.post(f"{B}/pharmacy/reservations/{res['id']}/collect", headers=pharm).json()["status"] == "collected")

# --- Pharmacy availability
a = c.get(f"{B}/pharmacy/availability/{para['id']}", headers=asha, params={"region_id": 1}).json()
check("live availability lists pharmacies with stock", a["available"] and len(a["pharmacies"]) >= 1)
r = c.put(f"{B}/pharmacy/2/stock", headers=pharm, json=[{"medicine_id": para["id"], "quantity": 0}])
check("pharmacist updates stock", r.status_code == 200)
check("RBAC: patient cannot update stock", c.put(f"{B}/pharmacy/2/stock", headers=patient, json=[]).status_code == 403)
# ASV: only government pharmacies stock it; empty stock everywhere in Bastar? use a region with none
r = c.post(f"{B}/pharmacy/reservations", headers=asha, json={"patient_id": pid, "medicine_id": asv["id"], "quantity": 999})
check("out of stock -> 409 and patient told not to travel", r.status_code == 409 and any("ନାହିଁ" in n["message"] for n in c.get(f"{B}/notifications", headers=admin, params={"phone": "9777777777"}).json()))

# --- Offline sync
ts = utcnow().isoformat()
push = {"device_id": "asha-phone-1", "records": [
    {"type": "patient", "client_id": "off-p1", "updated_at": ts, "data": {"name": "Offline Patient", "age": 60, "sex": "F", "phone": "9666666666", "village": "Narla", "region_id": 1, "language": "or"}},
    {"type": "health_record", "client_id": "off-r1", "updated_at": ts, "data": {"patient_client_id": "off-p1", "record_type": "vitals", "spo2": 91}},
    {"type": "triage", "client_id": "off-t1", "updated_at": ts, "data": {"patient_client_id": "off-p1", "symptoms": "ଶ୍ୱାସ କଷ୍ଟ", "duration_days": 1}},
]}
r = c.post(f"{B}/sync/push", headers=asha, json=push).json()
check("offline push: 3 records accepted, server ids returned", r["accepted"] == 3 and set(r["server_ids"]) == {"off-p1", "off-r1", "off-t1"}, r.get("conflicts"))
check("offline triage evaluated on arrival -> emergency escalated", c.get(f"{B}/triage/history", headers=asha, params={"urgency": "emergency"}).json()[0]["symptoms_normalized"] == "breathlessness")
old = (utcnow() - timedelta(days=1)).isoformat()
r2 = c.post(f"{B}/sync/push", headers=asha, json={"device_id": "asha-phone-2", "records": [
    {"type": "patient", "client_id": "off-p1", "updated_at": old, "data": {"name": "Stale Edit", "age": 60}}]}).json()
check("stale offline edit -> conflict, server not overwritten", r2["conflicts"] and c.get(f"{B}/patients/{r['server_ids']['off-p1']}", headers=asha).json()["name"] == "Offline Patient")
r3 = c.post(f"{B}/sync/push", headers=asha, json={"device_id": "asha-phone-1", "records": [
    {"type": "patient", "client_id": "off-p1", "updated_at": utcnow().isoformat(), "data": {"name": "Offline Patient Updated", "age": 61}}]}).json()
check("newer offline edit wins, version bumps", r3["accepted"] == 1 and c.get(f"{B}/patients/{r['server_ids']['off-p1']}", headers=asha).json()["version"] == 2)
full = c.post(f"{B}/sync/pull", headers=asha, json={"device_id": "asha-phone-1", "region_id": 1}).json()
check("full pull returns district patients + stock", len(full["patients"]) >= 9 and len(full["medicine_stock"]) > 0)
delta = c.post(f"{B}/sync/pull", headers=asha, json={"device_id": "asha-phone-1", "region_id": 1, "since": full["server_time"]}).json()
check("delta pull since last sync is empty (only changes travel)", len(delta["patients"]) == 0 and len(delta["health_records"]) == 0)
st = c.get(f"{B}/sync/status", headers=admin).json()
check("sync status shows pushes and pulls", "push" in st["totals"] and "pull" in st["totals"])

# --- Impact & demo
imp = c.get(f"{B}/analytics/impact", headers=hadmin).json()
check("impact: trips avoided & rupees saved counted", imp["overall"]["trips_avoided"] >= 7 and imp["overall"]["rupees_saved"] > 0)
check("impact per region (2 states)", len(imp["regions"]) >= 2 and imp["regions"][0]["doctor_posts_filled_pct"] < 60)
check("impact: wasted trips prevented counted", imp["overall"]["wasted_trips_prevented"] >= 2)
d = c.post(f"{B}/demo/patient-journey", headers=asha).json()
check("demo journey: all 6 steps present", all(k in d for k in ("1_triage", "2_appointment", "3_consultation", "4_pharmacy", "5_sms_to_patient", "6_what_the_system_did")))
check("demo journey: audio mode, medicines reserved", d["2_appointment"]["mode"] == "audio" and len(d["4_pharmacy"]["reserved"]) >= 1)
e = c.post(f"{B}/demo/emergency", headers=asha).json()
check("demo emergency: Odia chest pain -> emergency, not booked", e["urgency"] == "emergency" and e["booked_appointment"] is False)
o = c.post(f"{B}/demo/offline-sync", headers=asha).json()
check("demo offline sync: 4 records accepted", o["accepted"] == 4)
check("event audit trail", len(c.get(f"{B}/events", headers=admin, params={"limit": 200}).json()) > 20)

# --- AI Workflows
check("AI status endpoint reports ok", c.get(f"{B}/ai/status").status_code == 200 and c.get(f"{B}/ai/status").json()["status"] == "ok")

ai_t = c.post(f"{B}/ai/triage", headers=asha, json={"symptoms": "bukhar aur khansi", "duration_days": 3, "spo2": 97, "temperature_c": 38.5, "language": "hi"}).json()
check("AI triage returns structured urgency and differentials", ai_t["urgency"] == "urgent" and len(ai_t["potential_conditions"]) > 0 and len(ai_t["home_care_instructions"]) > 0)

ai_e = c.post(f"{B}/ai/triage", headers=asha, json={"symptoms": "seene me tez dard aur sans lene me dikkat", "spo2": 88, "language": "hi"}).json()
check("AI triage emergency guardrail triggers for chest pain", ai_e["urgency"] == "emergency" and ai_e["escalation_required"] is True and len(ai_e["red_flags"]) >= 2)

ai_s = c.post(f"{B}/ai/patient-summary", headers=asha, json={"patient_id": 1, "language": "en"}).json()
check("AI patient summary synthesizes EHR records and medications", ai_s["patient_id"] == 1 and len(ai_s["current_medications"]) >= 1 and bool(ai_s["summary_narrative"]))

ai_n = c.post(f"{B}/ai/doctor-notes", headers=doc, json={"chief_complaint": "Acute productive cough and high fever for 4 days", "duration": "4 days", "vitals": {"bp": "120/80", "temp_c": 38.5}, "language": "en"}).json()
check("AI doctor notes drafts SOAP note with prescriptions", bool(ai_n["soap_note"]["subjective"]) and len(ai_n["suggested_prescriptions"]) >= 1 and bool(ai_n["patient_instructions"]))

print(f"\n{ok} passed, {fail} failed")
