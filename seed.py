"""
seed.py  –  FILL THE DATABASE WITH DEMO DATA
==============================================
Run:  python seed.py      (WARNING: deletes telehealth.db and recreates it)

Creates 2 districts (Kalahandi, Odisha + Bastar, Chhattisgarh - to show it scales), 4 hospitals,
8 doctors (Odia/Hindi/English speakers, online/offline, with today's & tomorrow's slots),
6 pharmacies with live stock of 15 essential medicines (with Hindi & Odia names), 14 patients across
villages, and a handful of past consultations so the impact dashboard isn't empty.

All logins use password 1234.
"""
import random
from datetime import timedelta

from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import (Appointment, AvailabilitySlot, Consultation, Doctor, HealthRecord, Hospital, ImpactEvent,
                        Medicine, Patient, Pharmacy, PharmacyStock, Region, User)
from app.services.integration import utcnow

random.seed(7)
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
db = SessionLocal()
now = utcnow()
PW = hash_password("1234")

# ---------- Regions (add a district = one row) ----------
kal = Region(name="Kalahandi", district="Kalahandi", state="Odisha", primary_language="or", avg_travel_km=42, avg_travel_cost=450, avg_travel_hours=5)
bas = Region(name="Bastar", district="Bastar", state="Chhattisgarh", primary_language="hi", avg_travel_km=55, avg_travel_cost=520, avg_travel_hours=6)
db.add_all([kal, bas]); db.flush()

hospitals = [
    Hospital(name="District Headquarters Hospital, Bhawanipatna", region_id=kal.id, town="Bhawanipatna", phone="06670-230100", has_emergency=True, sanctioned_doctors=48, doctors_present=22),
    Hospital(name="CHC Lanjigarh", region_id=kal.id, town="Lanjigarh", phone="06670-244010", has_emergency=False, sanctioned_doctors=6, doctors_present=2),
    Hospital(name="CHC Thuamul Rampur", region_id=kal.id, town="Thuamul Rampur", phone="06670-245020", has_emergency=False, sanctioned_doctors=5, doctors_present=1),
    Hospital(name="Maharani Hospital, Jagdalpur", region_id=bas.id, town="Jagdalpur", phone="07782-222100", has_emergency=True, sanctioned_doctors=40, doctors_present=19),
]
db.add_all(hospitals); db.flush()

# ---------- Users ----------
def user(name, phone, role, lang, region=None, email=None):
    u = User(name=name, phone=phone, email=email, hashed_password=PW, role=role, preferred_language=lang, region_id=region)
    db.add(u); db.flush(); return u

admin = user("Admin", "9000000000", "admin", "en", email="admin@technexus.io")
hadmin = user("Dr Pradhan (CDMO)", "9000000001", "hospital_admin", "en", kal.id)
asha1 = user("Kamala Majhi (ASHA)", "9000000010", "health_worker", "or", kal.id)
asha2 = user("Sita Baghel (ASHA)", "9000000011", "health_worker", "hi", bas.id)
pharm1 = user("Ramesh Sahu (Pharmacist)", "9000000020", "pharmacist", "or", kal.id)
pharm2 = user("Jan Aushadhi Bhawanipatna", "9000000021", "pharmacist", "or", kal.id)
pat_user = user("Laxmi Nayak", "9000000030", "patient", "or", kal.id)

doc_specs = [
    ("Dr Anita Sahu", "9000000040", "general_medicine", "or,hi,en", hospitals[0], True),
    ("Dr Ravi Panda", "9000000041", "pediatrics", "or,en", hospitals[0], True),
    ("Dr Meera Das", "9000000042", "obstetrics", "or,hi", hospitals[0], False),
    ("Dr Suresh Behera", "9000000043", "general_medicine", "or", hospitals[1], True),
    ("Dr Nikhil Rao", "9000000044", "cardiology", "hi,en", hospitals[0], True),
    ("Dr Priya Mishra", "9000000045", "dermatology", "hi,en", None, True),          # tele-only volunteer
    ("Dr Arjun Thakur", "9000000046", "general_medicine", "hi", hospitals[3], True),
    ("Dr Kavita Netam", "9000000047", "pediatrics", "hi", hospitals[3], False),
]
doctors = []
for name, phone, spec, langs, hosp, online in doc_specs:
    u = user(name, phone, "doctor", langs.split(",")[0], hosp.region_id if hosp else None)
    d = Doctor(user_id=u.id, hospital_id=hosp.id if hosp else None, specialty=spec, languages=langs, is_online=online,
               qualification="MD" if spec != "general_medicine" else "MBBS", total_consultations=random.randint(5, 60))
    db.add(d); doctors.append(d)
db.flush()

# slots: today (from next hour) and tomorrow, morning + evening
for d in doctors:
    for day in (0, 1, 2):
        base = (now + timedelta(days=day)).replace(minute=0, second=0, microsecond=0)
        for start_h, end_h in ((10, 13), (16, 19)):
            s = base.replace(hour=start_h); e = base.replace(hour=end_h)
            if e <= now:
                continue
            db.add(AvailabilitySlot(doctor_id=d.id, start_time=max(s, now + timedelta(minutes=30)) if day == 0 else s, end_time=e,
                                    capacity=random.choice([4, 6, 8]), modes="video,audio,text"))
db.flush()

# ---------- Medicines (with Hindi & Odia names) ----------
meds_data = [
    ("Paracetamol 500mg", "Paracetamol", "पैरासिटामोल", "ପାରାସିଟାମଲ", "tablet", 2),
    ("Amoxicillin 500mg", "Amoxicillin", "एमोक्सिसिलिन", "ଆମକ୍ସିସିଲିନ", "capsule", 8),
    ("ORS sachet", "Oral Rehydration Salts", "ओआरएस", "ଓଆରଏସ", "sachet", 5),
    ("Zinc 20mg", "Zinc sulphate", "जिंक", "ଜିଙ୍କ", "tablet", 3),
    ("Metformin 500mg", "Metformin", "मेटफॉर्मिन", "ମେଟଫର୍ମିନ", "tablet", 2),
    ("Amlodipine 5mg", "Amlodipine", "एम्लोडिपिन", "ଆମ୍ଲୋଡିପିନ", "tablet", 3),
    ("Iron-Folic Acid", "Ferrous sulphate + folic acid", "आयरन फोलिक एसिड", "ଆଇରନ ଫୋଲିକ ଏସିଡ", "tablet", 1),
    ("Cetirizine 10mg", "Cetirizine", "सेटीरिज़िन", "ସେଟିରିଜିନ", "tablet", 2),
    ("Azithromycin 500mg", "Azithromycin", "एज़िथ्रोमाइसिन", "ଏଜିଥ୍ରୋମାଇସିନ", "tablet", 12),
    ("Salbutamol inhaler", "Salbutamol", "साल्बुटामोल इनहेलर", "ସାଲବୁଟାମଲ ଇନହେଲର", "inhaler", 120),
    ("Chloroquine 250mg", "Chloroquine", "क्लोरोक्वीन", "କ୍ଲୋରୋକ୍ୱିନ", "tablet", 4),
    ("Albendazole 400mg", "Albendazole", "एल्बेंडाजोल", "ଆଲବେଣ୍ଡାଜୋଲ", "tablet", 3),
    ("Insulin (regular)", "Human insulin", "इंसुलिन", "ଇନସୁଲିନ", "injection", 180),
    ("Anti-snake venom", "ASV", "सर्पदंश रोधी", "ସର୍ପ ବିଷ ପ୍ରତିରୋଧକ", "injection", 900),
    ("Cough syrup", "Dextromethorphan", "खांसी की दवा", "କାଶ ଔଷଧ", "syrup", 45),
]
meds = [Medicine(name=n, generic_name=g, name_hi=h, name_or=o, form=f, typical_price=p) for n, g, h, o, f, p in meds_data]
db.add_all(meds); db.flush()

# ---------- Pharmacies + stock ----------
pharmacies = [
    Pharmacy(name="Jan Aushadhi Kendra, Bhawanipatna", region_id=kal.id, village="Bhawanipatna", phone="9400000001", owner_user_id=pharm2.id, is_government=True),
    Pharmacy(name="Sahu Medical Store, Lanjigarh", region_id=kal.id, village="Lanjigarh", phone="9400000002", owner_user_id=pharm1.id),
    Pharmacy(name="PHC Dispensary, Thuamul Rampur", region_id=kal.id, village="Thuamul Rampur", phone="9400000003", is_government=True),
    Pharmacy(name="Maa Manikeswari Medicals, Kesinga", region_id=kal.id, village="Kesinga", phone="9400000004"),
    Pharmacy(name="Jan Aushadhi Kendra, Jagdalpur", region_id=bas.id, village="Jagdalpur", phone="9400000005", is_government=True),
    Pharmacy(name="Baghel Medicals, Kondagaon", region_id=bas.id, village="Kondagaon", phone="9400000006"),
]
db.add_all(pharmacies); db.flush()
for ph in pharmacies:
    for m in meds:
        # small village shops don't stock insulin / ASV; Jan Aushadhi is cheaper
        if m.name in ("Insulin (regular)", "Anti-snake venom") and not ph.is_government:
            continue
        qty = 0 if random.random() < 0.12 else random.randint(5, 120)
        db.add(PharmacyStock(pharmacy_id=ph.id, medicine_id=m.id, quantity=qty,
                             price=round(m.typical_price * (0.6 if ph.is_government else 1.0), 1),
                             updated_at=now - timedelta(hours=random.randint(1, 30))))
db.flush()

# ---------- Patients ----------
villages_kal = ["Lanjigarh", "Thuamul Rampur", "Kesinga", "Junagarh", "Narla", "Bhawanipatna"]
villages_bas = ["Kondagaon", "Jagdalpur", "Tokapal", "Bakawand"]
names = ["Laxmi Nayak", "Gopal Majhi", "Bhima Naik", "Sabitri Sahu", "Dhaneswar Behera", "Puni Bhoi", "Rukmini Harijan",
         "Jagannath Pradhan", "Manju Netam", "Budhram Baghel", "Sukhmati Markam", "Ramlal Kashyap", "Tulasi Mirdha", "Kishore Sahu"]
patients = []
for i, n in enumerate(names):
    kal_side = i < 9
    p = Patient(name=n, age=random.choice([3, 8, 24, 29, 34, 41, 52, 58, 67, 71]), sex=random.choice(["F", "M"]),
                phone=f"98{i:08d}", village=random.choice(villages_kal if kal_side else villages_bas),
                region_id=kal.id if kal_side else bas.id, language="or" if kal_side else "hi",
                chronic_conditions=random.choice(["", "", "diabetes", "hypertension", "asthma"]),
                registered_by=asha1.id if kal_side else asha2.id, user_id=pat_user.id if i == 0 else None)
    if i == 0:
        p.phone = pat_user.phone; p.age = 34; p.sex = "F"; p.village = "Lanjigarh"
    patients.append(p)
db.add_all(patients); db.flush()

# some history: vitals + past completed consultations so the impact dashboard has numbers
for p in random.sample(patients, 8):
    db.add(HealthRecord(patient_id=p.id, record_type="vitals", title="ASHA home visit", recorded_by=asha1.id,
                        temperature_c=round(random.uniform(36.5, 38.5), 1), bp_systolic=random.randint(110, 150),
                        bp_diastolic=random.randint(70, 95), pulse=random.randint(64, 96), spo2=random.randint(94, 99),
                        created_at=now - timedelta(days=random.randint(2, 40))))
for i in range(6):
    p = random.choice(patients); d = random.choice([x for x in doctors if x.specialty == "general_medicine"])
    when = now - timedelta(days=random.randint(3, 30))
    ap = Appointment(patient_id=p.id, doctor_id=d.id, scheduled_at=when, status="completed", mode=random.choice(["audio", "audio", "video", "text"]),
                     reason="fever", booked_by=asha1.id, created_at=when - timedelta(hours=random.randint(1, 20)))
    db.add(ap); db.flush()
    db.add(Consultation(appointment_id=ap.id, patient_id=p.id, doctor_id=d.id, mode=ap.mode, room_id=f"thb-hist{i}", status="completed",
                        started_at=when, ended_at=when + timedelta(minutes=12), diagnosis="Viral fever", wait_minutes=random.randint(20, 240)))
    reg = db.get(Region, p.region_id)
    db.add_all([ImpactEvent(region_id=p.region_id, patient_id=p.id, event_type="remote_consultation", value=1),
                ImpactEvent(region_id=p.region_id, patient_id=p.id, event_type="trip_avoided", value=reg.avg_travel_km),
                ImpactEvent(region_id=p.region_id, patient_id=p.id, event_type="money_saved", value=reg.avg_travel_cost),
                ImpactEvent(region_id=p.region_id, patient_id=p.id, event_type="wait_minutes", value=random.randint(20, 240))])
db.commit()

creds = [("admin@technexus.io (or 9000000000)", "admin"), ("9000000001", "hospital_admin"), ("9000000010", "health_worker (Kalahandi)"),
         ("9000000011", "health_worker (Bastar)"), ("9000000020", "pharmacist"), ("9000000030", "patient (Laxmi Nayak)"),
         ("9000000040", "doctor (Dr Anita Sahu, general)"), ("9000000041", "doctor (Dr Ravi Panda, pediatrics)")]
db.close()
print("Seeded. Login (password for everyone: 1234):")
for login, role in creds:
    print(f"  {login:36s} {role}")
