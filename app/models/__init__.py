"""
app/models/__init__.py  –  imports every table class in one place.
`import app.models` anywhere = all tables registered with SQLAlchemy. Add new models here too.
"""
from app.models.core import Hospital, Region, User  # noqa
from app.models.patients import HealthRecord, Patient, Prescription, PrescriptionItem  # noqa
from app.models.clinical import Appointment, AvailabilitySlot, Consultation, Doctor  # noqa
from app.models.pharmacy import Medicine, MedicineReservation, Pharmacy, PharmacyStock  # noqa
from app.models.support import EventLog, ImpactEvent, Notification, SyncLog, TriageResult  # noqa
