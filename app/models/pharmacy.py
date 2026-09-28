"""
app/models/pharmacy.py  –  MEDICINES, PHARMACIES, STOCK, RESERVATIONS
=======================================================================
The PS: "real-time medicine-availability updates from local pharmacies, so patients aren't sent
on a wasted trip".

Medicine             = the drug, with names in Hindi and Odia so a villager can search in their language
Pharmacy             = a shop, belongs to a region, has a village
PharmacyStock        = how many of which medicine each pharmacy has RIGHT NOW (pharmacist updates it)
MedicineReservation  = "hold 10 tablets of Paracetamol for patient X till tomorrow" → no wasted trip
"""
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.database import Base
from app.models.core import now


class Medicine(Base):
    __tablename__ = "medicines"
    id = Column(Integer, primary_key=True)
    name = Column(String(120), nullable=False)          # "Paracetamol 500mg"
    generic_name = Column(String(120), default="")
    name_hi = Column(String(120), default="")           # पैरासिटामोल
    name_or = Column(String(120), default="")           # ପାରାସିଟାମଲ
    form = Column(String(30), default="tablet")         # tablet | syrup | injection | drops
    is_essential = Column(Boolean, default=True)        # on the national essential medicines list
    typical_price = Column(Float, default=10.0)


class Pharmacy(Base):
    __tablename__ = "pharmacies"
    id = Column(Integer, primary_key=True)
    name = Column(String(160), nullable=False)
    region_id = Column(Integer, ForeignKey("regions.id"), nullable=False)
    village = Column(String(120), default="")
    phone = Column(String(20), default="")
    owner_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_government = Column(Boolean, default=False)      # Jan Aushadhi / PHC dispensary
    open_hours = Column(String(60), default="08:00-20:00")

    stock = relationship("PharmacyStock", back_populates="pharmacy")


class PharmacyStock(Base):
    __tablename__ = "pharmacy_stock"
    id = Column(Integer, primary_key=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    quantity = Column(Integer, default=0)
    price = Column(Float, default=10.0)
    updated_at = Column(DateTime, default=now, onupdate=now)

    pharmacy = relationship("Pharmacy", back_populates="stock")
    medicine = relationship("Medicine")


class MedicineReservation(Base):
    __tablename__ = "medicine_reservations"
    id = Column(Integer, primary_key=True)
    pharmacy_id = Column(Integer, ForeignKey("pharmacies.id"), nullable=False)
    medicine_id = Column(Integer, ForeignKey("medicines.id"), nullable=False)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    prescription_id = Column(Integer, ForeignKey("prescriptions.id"), nullable=True)
    quantity = Column(Integer, nullable=False)
    status = Column(String(20), default="reserved")     # reserved | collected | cancelled | expired
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=now)
