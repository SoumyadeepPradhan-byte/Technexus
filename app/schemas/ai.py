"""
app/schemas/ai.py  –  STRUCTURED SCHEMAS FOR AI WORKFLOWS
===========================================================
Defines Pydantic v2 request and response schemas for:
  1. Medical & Symptom Triage (urgency, clinical differential, red flags, reasoning)
  2. Patient Summary Generation (clinical narrative, vitals trend, medication reconciliation)
  3. Doctor Note Drafting (SOAP notes, structured prescriptions, patient discharge advice)
  4. AI Service Status & Diagnostics
"""
from typing import Any, Optional
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# 1. Medical & Symptom Triage Schemas
# ─────────────────────────────────────────────────────────────────────────────
class AIMedicalTriageRequest(BaseModel):
    symptoms: str | list[str] = Field(
        ...,
        description="Symptoms described in free text or list (English, Hindi, Hinglish, Odia, etc.)"
    )
    age: Optional[int] = Field(default=None, ge=0, le=120, description="Patient age in years")
    sex: str = Field(default="F", description="Biological sex (M, F, O)")
    duration_days: int = Field(default=1, ge=0, description="Duration of symptoms in days")
    spo2: Optional[int] = Field(default=None, ge=40, le=100, description="Oxygen saturation SpO2 percentage")
    temperature_c: Optional[float] = Field(default=None, ge=30.0, le=45.0, description="Body temperature in Celsius")
    bp_systolic: Optional[int] = Field(default=None, ge=40, le=260, description="Systolic blood pressure mmHg")
    bp_diastolic: Optional[int] = Field(default=None, ge=30, le=160, description="Diastolic blood pressure mmHg")
    pulse: Optional[int] = Field(default=None, ge=30, le=240, description="Pulse / heart rate in bpm")
    is_pregnant: bool = Field(default=False, description="Whether patient is currently pregnant")
    medical_history: Optional[str] = Field(default="", description="Known chronic illnesses or past conditions")
    current_medications: Optional[str] = Field(default="", description="Current medications taken by patient")
    allergies: Optional[str] = Field(default="", description="Known drug or environmental allergies")
    patient_id: Optional[int] = Field(default=None, description="Optional existing patient ID to pull clinical records")
    language: Optional[str] = Field(default="en", description="Target language ('en', 'hi', 'or')")


class AIMedicalTriageResponse(BaseModel):
    urgency: str = Field(
        ...,
        description="Clinical urgency classification: 'self_care', 'routine', 'urgent', 'emergency'"
    )
    escalation_required: bool = Field(
        ...,
        description="True if critical emergency escalation or ambulance transfer is required"
    )
    recommended_action: str = Field(
        ...,
        description="Clear primary clinical directive for patient or health worker"
    )
    recommended_specialty: str = Field(
        ...,
        description="Recommended clinical specialty (e.g. general_medicine, pediatrics, cardiology, emergency)"
    )
    red_flags: list[str] = Field(
        default_factory=list,
        description="Detected critical danger signs (e.g., chest pain, respiratory distress, low SpO2)"
    )
    potential_conditions: list[str] = Field(
        default_factory=list,
        description="Differential diagnoses / clinical conditions to consider"
    )
    clinical_reasoning: str = Field(
        ...,
        description="Evidence-based clinical justification for triage level and recommendations"
    )
    home_care_instructions: list[str] = Field(
        default_factory=list,
        description="Supportive home care and symptom relief measures"
    )
    warning_signs_to_escalate: list[str] = Field(
        default_factory=list,
        description="Specific worsening warning signs that require emergency hospital care"
    )
    disclaimer: str = Field(
        ...,
        description="Standard medical disclaimer (AI assistant guidance, not a definitive diagnosis)"
    )
    model_name: str = Field(
        ...,
        description="Name of the model or engine that evaluated this request"
    )
    fallback_used: bool = Field(
        ...,
        description="True if deterministic clinical safety fallback was executed"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Patient Summary Generation Schemas
# ─────────────────────────────────────────────────────────────────────────────
class AIPatientSummaryRequest(BaseModel):
    patient_id: Optional[int] = Field(
        default=None,
        description="Patient ID to automatically fetch all health records, vitals, prescriptions, and triages"
    )
    patient_name: Optional[str] = Field(default=None, description="Patient name if providing direct context")
    age: Optional[int] = Field(default=None, ge=0, le=120)
    sex: Optional[str] = Field(default=None)
    chronic_conditions: Optional[str] = Field(default=None, description="e.g. 'Type 2 Diabetes, Hypertension'")
    allergies: Optional[str] = Field(default=None, description="e.g. 'Penicillin, NSAIDs'")
    clinical_notes_history: Optional[list[str]] = Field(
        default_factory=list,
        description="Additional visit notes or historical observations"
    )
    recent_vitals: Optional[dict[str, Any]] = Field(
        default=None,
        description="Observed vitals (e.g. {'bp': '138/88', 'spo2': 98, 'temp_c': 37.1})"
    )
    recent_prescriptions: Optional[list[str]] = Field(
        default_factory=list,
        description="List of active or recent medications"
    )
    focus: str = Field(
        default="clinical_overview",
        description="Summary focus: 'clinical_overview', 'handover', 'patient_friendly'"
    )
    language: str = Field(default="en", description="Target language ('en', 'hi', 'or')")


class AIPatientSummaryResponse(BaseModel):
    patient_id: Optional[int] = Field(default=None, description="Patient ID if linked in database")
    patient_name: Optional[str] = Field(default=None, description="Patient name")
    summary_narrative: str = Field(
        ...,
        description="Holistic clinical narrative summarizing patient status, trends, and current clinical picture"
    )
    key_medical_history: list[str] = Field(
        default_factory=list,
        description="Chronic diseases, prior major diagnoses, and relevant medical background"
    )
    active_concerns_and_symptoms: list[str] = Field(
        default_factory=list,
        description="Current complaints, recent triage episodes, or unstable symptoms"
    )
    allergies_and_contraindications: list[str] = Field(
        default_factory=list,
        description="Allergies and high-risk medication contraindications"
    )
    vitals_analysis: str = Field(
        ...,
        description="Trend analysis of blood pressure, oxygenation, pulse, and temperature"
    )
    current_medications: list[str] = Field(
        default_factory=list,
        description="Active medication list with reconciled dosages"
    )
    recommended_clinical_next_steps: list[str] = Field(
        default_factory=list,
        description="Priority action items for upcoming consultation, diagnostic tests, or therapy adjustment"
    )
    risk_level: str = Field(
        ...,
        description="Overall patient risk stratification: 'low', 'moderate', 'high', 'critical'"
    )
    model_name: str = Field(..., description="Engine used to generate summary")
    fallback_used: bool = Field(..., description="Whether rule-based synthesis fallback was used")


# ─────────────────────────────────────────────────────────────────────────────
# 3. Doctor Note Drafting Schemas (SOAP)
# ─────────────────────────────────────────────────────────────────────────────
class AIPrescriptionSuggestion(BaseModel):
    medicine_name: str = Field(..., description="Generic or brand name of medication (e.g. Paracetamol)")
    dosage: str = Field(..., description="Dosage (e.g. '500 mg')")
    frequency: str = Field(..., description="Dosing schedule (e.g. '1-0-1' or 'TDS after meals')")
    duration_days: int = Field(default=5, ge=1, description="Duration of therapy in days")
    instructions: str = Field(default="", description="Specific patient instructions (e.g. 'after meals with warm water')")


class SOAPNote(BaseModel):
    subjective: str = Field(
        ...,
        description="History of Present Illness (HPI), chief complaint, symptoms timeline, and patient statements"
    )
    objective: str = Field(
        ...,
        description="Vital signs, physical exam findings, general appearance, and laboratory results"
    )
    assessment: str = Field(
        ...,
        description="Primary clinical diagnosis, differential diagnoses, and disease severity assessment"
    )
    plan: str = Field(
        ...,
        description="Diagnostic investigations, pharmacological interventions, lifestyle counseling, and warnings"
    )


class AIDoctorNoteDraftRequest(BaseModel):
    patient_id: Optional[int] = Field(default=None, description="Optional patient ID to pull clinical history")
    consultation_id: Optional[int] = Field(default=None, description="Optional consultation session ID")
    chief_complaint: str = Field(
        ...,
        description="Primary presenting complaint (e.g. 'High fever and productive cough for 3 days')"
    )
    symptoms_and_history: Optional[str] = Field(
        default="",
        description="Detailed patient symptoms, onset, progression, and past medical history"
    )
    duration: Optional[str] = Field(default="", description="Duration string (e.g. '3 days')")
    vitals: Optional[dict[str, Any]] = Field(
        default=None,
        description="Vital signs observed during consult (e.g. {'bp': '124/82', 'spo2': 97, 'temp_c': 38.4, 'pulse': 88})"
    )
    physical_examination: Optional[str] = Field(
        default="",
        description="Doctor's objective examination findings (e.g. 'Bilateral chest clear, pharynx mild erythema')"
    )
    raw_dictation_or_notes: Optional[str] = Field(
        default="",
        description="Raw doctor dictation, rough bullet notes, or telemedicine audio transcription"
    )
    clinical_impression: Optional[str] = Field(
        default="",
        description="Physician's suspected impression or working diagnosis"
    )
    language: str = Field(default="en", description="Output language for notes and patient advice ('en', 'hi', 'or')")


class AIDoctorNoteDraftResponse(BaseModel):
    chief_complaint: str = Field(..., description="Chief complaint")
    soap_note: SOAPNote = Field(..., description="Structured SOAP clinical documentation")
    suggested_prescriptions: list[AIPrescriptionSuggestion] = Field(
        default_factory=list,
        description="Suggested medications with recommended dosages and intervals"
    )
    patient_instructions: str = Field(
        ...,
        description="Patient-accessible, compassionate explanation of treatment instructions and red flags"
    )
    follow_up_recommendation: str = Field(
        ...,
        description="Follow-up timeline and criteria for immediate return"
    )
    e_prescription_ready: bool = Field(
        default=True,
        description="Ready for one-click pharmacy electronic reservation"
    )
    summary: str = Field(
        ...,
        description="Concise one-line summary for clinical audit and quick EHR reference"
    )
    model_name: str = Field(..., description="Model or engine utilized")
    fallback_used: bool = Field(..., description="Whether deterministic clinical engine fallback was used")


# ─────────────────────────────────────────────────────────────────────────────
# 4. Diagnostics & Health
# ─────────────────────────────────────────────────────────────────────────────
class AIHealthStatusOut(BaseModel):
    status: str = Field(default="ok", description="AI service health status")
    configured_provider: str = Field(..., description="Configured LLM provider ('openai', 'anthropic', 'gemini', 'fallback_only')")
    model: str = Field(..., description="Active LLM model name")
    has_api_key: bool = Field(..., description="Whether an active LLM API key is detected in the environment")
    timeout_seconds: int = Field(..., description="Configured timeout safety window for external LLM requests")
    fallback_engine_ready: bool = Field(default=True, description="Deterministic rule-based clinical engine readiness")
    supported_workflows: list[str] = Field(
        default_factory=lambda: ["medical_triage", "patient_summary", "doctor_note_drafting"],
        description="List of enabled AI workflows"
    )
