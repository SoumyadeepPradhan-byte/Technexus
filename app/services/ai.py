"""
app/services/ai.py  –  AI WORKFLOW ENGINES & LLM INTEGRATION
==============================================================
Provides production-grade AI services for the Telehealth Bridge:
  1. Medical & Symptom Triage with clinical safety guardrails & red-flag detection
  2. Patient Clinical Summary Generation (integrating records, vitals, prescriptions)
  3. Doctor SOAP Note Drafting with prescription recommendations and patient instructions
  4. Resilient timeout safety, multi-provider LLM support, and deterministic fallback engines

CLINICAL SAFETY INVARIANTS:
  - Emergency red flags (chest pain, breathlessness, seizure, snake bite, SpO2 < 90, etc.)
    ALWAYS override model outputs and trigger emergency escalation.
  - Vulnerable populations (children < 5, adults > 65, pregnancy) are never left at self-care.
  - If external model calls fail, time out, or keys are dummy/absent, deterministic clinical
    rules and synthesis engines take over immediately with zero downtime.
"""
import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from app.ai.triage import assess_symptoms
from app.core.config import settings
from app.models import (
    EventLog,
    HealthRecord,
    Medicine,
    Patient,
    Prescription,
    TriageResult,
    User,
)
from app.schemas.ai import (
    AIDoctorNoteDraftRequest,
    AIDoctorNoteDraftResponse,
    AIHealthStatusOut,
    AIMedicalTriageRequest,
    AIMedicalTriageResponse,
    AIPatientSummaryRequest,
    AIPatientSummaryResponse,
    AIPrescriptionSuggestion,
    SOAPNote,
)

logger = logging.getLogger("telehealth.ai")
T = TypeVar("T", bound=BaseModel)


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def log_ai_event(db: Optional[Session], event: str, detail: str = ""):
    """Log an AI automation action into the central audit trail."""
    if db is not None:
        try:
            db.add(EventLog(source_module="ai", event=event, detail=detail))
            db.flush()
        except Exception as e:
            logger.warning("Could not log AI event to DB: %s", e)


# ─────────────────────────────────────────────────────────────────────────────
# LLM Provider Detection & HTTP Client Helper
# ─────────────────────────────────────────────────────────────────────────────
def _is_valid_key(key: Optional[str]) -> bool:
    """Check if key is non-empty and not a dummy placeholder."""
    if not key:
        return False
    k = key.strip().lower()
    return not (k.startswith("dummy-") or k.startswith("your-") or k == "change-me" or len(k) < 8)


def get_active_llm_provider() -> tuple[str, str, str]:
    """
    Returns (provider_name, api_key, model_name).
    Supports OpenAI, Anthropic Claude, and Google Gemini.
    """
    if _is_valid_key(settings.OPENAI_API_KEY):
        return "openai", settings.OPENAI_API_KEY, settings.LLM_MODEL or "gpt-4o-mini"
    if _is_valid_key(settings.ANTHROPIC_API_KEY):
        return "anthropic", settings.ANTHROPIC_API_KEY, "claude-3-5-sonnet-20241022"
    if _is_valid_key(settings.GEMINI_API_KEY):
        return "gemini", settings.GEMINI_API_KEY, "gemini-1.5-flash"
    return "fallback", "", "clinical_rules_engine_v1"


def _clean_json_markdown(content: str) -> str:
    """Strip ```json ... ``` formatting markdown wrappers if present."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def call_llm_structured(
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T]
) -> tuple[T, str]:
    """
    Invokes external LLM with strict timeout safety and parses response into Pydantic model.
    Raises RuntimeError if LLM fails, times out, or cannot be parsed.
    """
    provider, api_key, model = get_active_llm_provider()
    if provider == "fallback":
        raise RuntimeError("No active external LLM provider configured; using clinical fallback engine.")

    timeout_seconds = max(5, settings.LLM_TIMEOUT_SECONDS)
    client_timeout = httpx.Timeout(timeout_seconds, connect=4.0)

    try:
        with httpx.Client(timeout=client_timeout) as client:
            if provider == "openai":
                base_url = (settings.OPENAI_BASE_URL.rstrip("/") if settings.OPENAI_BASE_URL
                            else "https://api.openai.com/v1")
                url = f"{base_url}/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                }
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]

            elif provider == "anthropic":
                url = "https://api.anthropic.com/v1/messages"
                headers = {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                }
                full_system = (
                    f"{system_prompt}\n"
                    "CRITICAL: Output ONLY a valid JSON object matching the requested schema. "
                    "Do NOT include markdown backticks or conversational explanations."
                )
                payload = {
                    "model": model,
                    "system": full_system,
                    "messages": [{"role": "user", "content": user_prompt}],
                    "max_tokens": 2048,
                    "temperature": 0.2,
                }
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = "".join(part.get("text", "") for part in data.get("content", []))

            elif provider == "gemini":
                # Using Gemini OpenAI-compatible or direct endpoint
                url = f"https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                }
                payload = {
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "response_format": {"type": "json_object"},
                    "temperature": 0.2,
                }
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]

            else:
                raise RuntimeError(f"Unsupported LLM provider: {provider}")

        # Parse and validate with Pydantic
        cleaned_json = _clean_json_markdown(raw_text)
        parsed_dict = json.loads(cleaned_json)
        validated_obj = response_model.model_validate(parsed_dict)
        return validated_obj, model

    except (httpx.TimeoutException, httpx.HTTPError, json.JSONDecodeError, ValidationError, Exception) as exc:
        logger.warning("LLM call via %s failed (%s); triggering clinical fallback.", provider, exc)
        raise RuntimeError(f"LLM call failure: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# 1. Medical & Symptom Triage Workflow
# ─────────────────────────────────────────────────────────────────────────────
def _build_triage_differential(normalized_codes: list[str]) -> list[str]:
    """Generate clinical differential diagnoses for normalized symptom codes."""
    differentials = []
    codes_set = set(normalized_codes)
    if "chest_pain" in codes_set:
        differentials.extend(["Acute Coronary Syndrome / Angina", "Gastroesophageal Reflux", "Costochondritis"])
    if "breathlessness" in codes_set:
        differentials.extend(["Asthma / Acute Bronchospasm", "Pneumonia", "Heart Failure / Pulmonary Edema"])
    if "fever" in codes_set and "cough" in codes_set:
        differentials.extend(["Acute Viral Bronchitis", "Upper Respiratory Tract Infection (URTI)", "Community-Acquired Pneumonia"])
    elif "fever" in codes_set:
        differentials.extend(["Viral Pyrexia", "Malaria / Dengue", "Urinary Tract Infection", "Typhoid Fever"])
    if "diarrhea" in codes_set or "vomiting" in codes_set:
        differentials.extend(["Acute Gastroenteritis", "Foodborne Illness", "Amebic Dysentery"])
    if "abdominal_pain" in codes_set:
        differentials.extend(["Acute Gastritis / Peptic Ulcer", "Appendicitis", "Biliary Colic"])
    if "headache" in codes_set:
        differentials.extend(["Tension Headache", "Migraine", "Sinusitis"])
    if "rash" in codes_set:
        differentials.extend(["Allergic Contact Dermatitis", "Viral Exanthem", "Urticaria"])
    if "snake_bite" in codes_set:
        differentials.extend(["Venomous Envenomation (Elapid/Viper)", "Dry Bite with Local Trauma"])

    if not differentials:
        differentials = ["Undifferentiated Acute Illness", "Symptomatic Viral Syndrome"]
    return list(dict.fromkeys(differentials))[:4]


def _build_home_care_and_warnings(urgency: str, normalized_codes: list[str], language: str) -> tuple[list[str], list[str]]:
    """Generate supportive care instructions and danger signs."""
    warnings = [
        "Inability to tolerate liquids or persistent vomiting",
        "Shortness of breath, chest tightness, or rapid breathing",
        "High fever not responding to antipyretics or lasting > 3 days",
        "Onset of confusion, extreme lethargy, or loss of consciousness",
    ]
    if "chest_pain" in normalized_codes or urgency == "emergency":
        warnings.insert(0, "Sudden severe chest pressure radiating to arm, neck, or jaw")
        home_care = [
            "Do NOT delay or attempt home treatment.",
            "Keep patient seated in a comfortable upright position.",
            "Loosen tight clothing and ensure fresh airflow.",
            "Arrange immediate emergency transport (Call 108).",
        ]
        return home_care, warnings

    home_care = [
        "Maintain adequate oral hydration with clean boiled water, ORS, or tender coconut water.",
        "Take plenty of rest and avoid strenuous physical labor.",
        "Eat light, easily digestible home-cooked meals.",
        "Monitor body temperature twice daily.",
    ]
    if "fever" in normalized_codes:
        home_care.append("Use warm sponge baths for high temperature; take Paracetamol if advised.")
    if "cough" in normalized_codes:
        home_care.append("Inhale steam and drink warm fluids or ginger-tulsi tea for throat soothing.")
    return home_care, warnings


def triage_medical_symptoms_ai(
    db: Session,
    request: AIMedicalTriageRequest,
    caller: Optional[User] = None
) -> AIMedicalTriageResponse:
    """
    Evaluates symptoms using AI with mandatory red-flag guardrails.
    Clinical safety invariants:
      - Emergency symptoms ALWAYS trigger emergency escalation.
      - Children < 5, elderly > 65, and pregnant patients are never left at self-care.
      - Vitals (SpO2 < 90, Temp >= 40) override benign self-reported text.
    """
    # 1. Fetch patient context if patient_id is provided
    patient: Optional[Patient] = None
    if request.patient_id:
        patient = db.get(Patient, request.patient_id)

    age = request.age if request.age is not None else (patient.age if patient else None)
    sex = request.sex or (patient.sex if patient else "F")
    is_pregnant = request.is_pregnant or (patient.is_pregnant if patient else False)
    lang = request.language or (patient.language if patient else None) or (caller.preferred_language if caller else "en")
    vitals_dict = {
        "spo2": request.spo2,
        "temperature_c": request.temperature_c,
        "bp_systolic": request.bp_systolic,
        "bp_diastolic": request.bp_diastolic,
        "pulse": request.pulse,
    }

    # 2. Hard Clinical Guardrails via assess_symptoms (Deterministic Baseline)
    rule_assessment = assess_symptoms(
        symptoms=request.symptoms,
        age=age,
        sex=sex,
        duration_days=request.duration_days,
        vitals=vitals_dict,
        is_pregnant=is_pregnant,
        language=lang,
        emergency_number=settings.EMERGENCY_NUMBER,
    )
    normalized_codes = rule_assessment["symptoms_normalized"]
    has_emergency_red_flags = len(rule_assessment["red_flags"]) > 0 or rule_assessment["urgency"] == "emergency"

    # 3. Attempt LLM Structured Assessment
    llm_result: Optional[AIMedicalTriageResponse] = None
    llm_model_name = ""
    fallback_used = False

    symptoms_text = (
        ", ".join(request.symptoms) if isinstance(request.symptoms, list) else str(request.symptoms)
    )
    med_history = request.medical_history or (patient.chronic_conditions if patient else "") or "None reported"
    allergies = request.allergies or (patient.allergies if patient else "") or "None known"

    system_prompt = (
        "You are an expert clinical triage physician in a rural telehealth network. "
        "Your highest duty is patient safety. Follow clinical protocol:\n"
        "- Classify urgency strictly into: 'self_care', 'routine', 'urgent', 'emergency'.\n"
        "- Red flags (chest pain, severe breathlessness, SpO2 < 90%, seizure, altered mental state, snake bite) MUST be 'emergency'.\n"
        "- Never falsely reassure. High fever > 3 days or cough > 2 weeks must be at least 'urgent'.\n"
        "- Return ONLY a valid JSON object matching the required schema."
    )
    user_prompt = (
        f"Patient Information:\n"
        f"- Age: {age}, Sex: {sex}, Pregnant: {is_pregnant}\n"
        f"- Symptoms: {symptoms_text} (Duration: {request.duration_days} days)\n"
        f"- Measured Vitals: SpO2={request.spo2}%, Temp={request.temperature_c}°C, BP={request.bp_systolic}/{request.bp_diastolic} mmHg, Pulse={request.pulse} bpm\n"
        f"- Medical History: {med_history}\n"
        f"- Allergies: {allergies}\n"
        f"- Response Language: {lang}\n\n"
        "Generate a complete triage response JSON with fields: urgency, escalation_required, "
        "recommended_action, recommended_specialty, red_flags, potential_conditions, "
        "clinical_reasoning, home_care_instructions, warning_signs_to_escalate, disclaimer, model_name, fallback_used."
    )

    try:
        validated_resp, llm_model_name = call_llm_structured(
            system_prompt, user_prompt, AIMedicalTriageResponse
        )
        llm_result = validated_resp
        llm_result.model_name = llm_model_name
        llm_result.fallback_used = False
    except Exception as exc:
        logger.info("Using deterministic triage engine: %s", exc)
        fallback_used = True

    # 4. Synthesize Final Clinical Response
    if llm_result and not fallback_used:
        final_response = llm_result
        # Enforce Clinical Guardrail: if deterministic red flags exist, FORCE emergency escalation
        if has_emergency_red_flags:
            final_response.urgency = "emergency"
            final_response.escalation_required = True
            final_response.recommended_specialty = "emergency"
            for rf in rule_assessment["red_flags"]:
                if rf not in final_response.red_flags:
                    final_response.red_flags.append(rf)
            if not final_response.warning_signs_to_escalate:
                final_response.warning_signs_to_escalate = rule_assessment["red_flags"]
        # Enforce vulnerable group bump
        if rule_assessment["vulnerable_group"] and final_response.urgency == "self_care":
            final_response.urgency = "routine"
    else:
        # Deterministic Clinical Engine Execution
        urgency = rule_assessment["urgency"]
        escalation = rule_assessment["escalation"]
        specialty = rule_assessment["recommended_specialty"]
        red_flags = rule_assessment["red_flags"]
        differentials = _build_triage_differential(normalized_codes)
        home_care, warnings = _build_home_care_and_warnings(urgency, normalized_codes, lang)

        # Build clinical reasoning
        reasoning_parts = []
        if red_flags:
            reasoning_parts.append(f"Immediate emergency escalation triggered due to critical indicators: {', '.join(red_flags)}.")
        elif rule_assessment["urgent_reasons"]:
            reasoning_parts.append(f"Urgent evaluation warranted due to: {', '.join(rule_assessment['urgent_reasons'])}.")
        if rule_assessment["vulnerable_group"]:
            reasoning_parts.append(f"Risk tier elevated because patient belongs to a vulnerable category ({', '.join(rule_assessment['vulnerable_group'])}).")
        if not reasoning_parts:
            reasoning_parts.append("Mild symptoms without physiological red flags; suitable for symptomatic home support and routine follow-up if symptoms persist.")

        final_response = AIMedicalTriageResponse(
            urgency=urgency,
            escalation_required=escalation,
            recommended_action=rule_assessment["recommended_action"],
            recommended_specialty=specialty,
            red_flags=red_flags,
            potential_conditions=differentials,
            clinical_reasoning=" ".join(reasoning_parts),
            home_care_instructions=home_care,
            warning_signs_to_escalate=warnings,
            disclaimer=rule_assessment["disclaimer"],
            model_name="clinical_rules_engine_v1",
            fallback_used=True,
        )

    # 5. Audit Logging
    log_ai_event(
        db,
        f"AI triage: {final_response.urgency}",
        f"patient_id={request.patient_id}; model={final_response.model_name}; fallback={final_response.fallback_used}"
    )
    return final_response


# ─────────────────────────────────────────────────────────────────────────────
# 2. Patient Summary Generation Workflow
# ─────────────────────────────────────────────────────────────────────────────
def generate_patient_summary_ai(
    db: Session,
    request: AIPatientSummaryRequest,
    caller: Optional[User] = None
) -> AIPatientSummaryResponse:
    """
    Synthesizes a cohesive clinical summary of patient health records, vitals trends,
    past triage checks, and active prescriptions.
    """
    patient: Optional[Patient] = None
    records: list[HealthRecord] = []
    prescriptions: list[Prescription] = []
    triages: list[TriageResult] = []

    if request.patient_id:
        patient = db.get(Patient, request.patient_id)
        if patient and not patient.is_deleted:
            records = (
                db.query(HealthRecord)
                .filter(HealthRecord.patient_id == patient.id, HealthRecord.is_deleted.is_(False))
                .order_by(HealthRecord.created_at.desc())
                .limit(10)
                .all()
            )
            prescriptions = (
                db.query(Prescription)
                .filter(Prescription.patient_id == patient.id, Prescription.is_deleted.is_(False))
                .order_by(Prescription.created_at.desc())
                .limit(5)
                .all()
            )
            triages = (
                db.query(TriageResult)
                .filter(TriageResult.patient_id == patient.id)
                .order_by(TriageResult.created_at.desc())
                .limit(5)
                .all()
            )

    # Compile context
    p_name = request.patient_name or (patient.name if patient else "Unknown Patient")
    p_age = request.age if request.age is not None else (patient.age if patient else "N/A")
    p_sex = request.sex or (patient.sex if patient else "N/A")
    p_chronic = request.chronic_conditions or (patient.chronic_conditions if patient else "") or "None recorded"
    p_allergies = request.allergies or (patient.allergies if patient else "") or "None recorded"

    # Extract all medicines from prescriptions
    med_list: list[str] = list(request.recent_prescriptions)
    for pr in prescriptions:
        for itm in pr.items:
            med_obj = db.get(Medicine, itm.medicine_id)
            med_name = med_obj.name if med_obj else f"Medicine #{itm.medicine_id}"
            entry = f"{med_name} {itm.dosage} ({itm.frequency}) for {itm.duration_days} days"
            if entry not in med_list:
                med_list.append(entry)

    # Extract vitals and trends
    vitals_history = []
    latest_vitals: dict[str, Any] = request.recent_vitals or {}
    for r in records:
        if r.bp_systolic or r.spo2 or r.temperature_c:
            v_str = (
                f"{r.created_at.strftime('%Y-%m-%d')}: "
                f"BP={r.bp_systolic}/{r.bp_diastolic or ''} mmHg, "
                f"SpO2={r.spo2}%, Temp={r.temperature_c}°C, Pulse={r.pulse} bpm"
            )
            vitals_history.append(v_str)
            if not latest_vitals:
                latest_vitals = {
                    "bp_systolic": r.bp_systolic,
                    "bp_diastolic": r.bp_diastolic,
                    "spo2": r.spo2,
                    "temperature_c": r.temperature_c,
                    "pulse": r.pulse,
                }

    # Extract active concerns
    active_concerns = []
    for tr in triages:
        active_concerns.append(f"Triage on {tr.created_at.strftime('%Y-%m-%d')}: {tr.symptoms_input} (Urgency: {tr.urgency})")
    for r in records:
        if r.title or r.content:
            active_concerns.append(f"Record: {r.title} - {r.content[:80]}")
    active_concerns.extend(request.clinical_notes_history)

    # Attempt LLM Summary
    system_prompt = (
        "You are an expert Chief Medical Officer summarizing telehealth patient records. "
        "Synthesize demographics, medical history, vitals trends, active medications, and acute complaints "
        "into a structured EHR summary. Emphasize clinical safety, potential drug interactions, and care gaps. "
        "Return ONLY a valid JSON object matching the requested schema."
    )
    user_prompt = (
        f"Patient Summary Request:\n"
        f"- Patient: {p_name}, Age: {p_age}, Sex: {p_sex}\n"
        f"- Chronic Conditions: {p_chronic}\n"
        f"- Allergies: {p_allergies}\n"
        f"- Vitals History: {'; '.join(vitals_history) or 'No historical vitals'}\n"
        f"- Latest Vitals: {latest_vitals or 'Not measured'}\n"
        f"- Recent Medications: {'; '.join(med_list) or 'None active'}\n"
        f"- Recent Events / Triages: {'; '.join(active_concerns[:5]) or 'No acute complaints'}\n"
        f"- Target Focus: {request.focus}\n"
        f"- Language: {request.language}\n\n"
        "Generate a complete JSON summary with fields: patient_id, patient_name, summary_narrative, "
        "key_medical_history, active_concerns_and_symptoms, allergies_and_contraindications, "
        "vitals_analysis, current_medications, recommended_clinical_next_steps, risk_level, model_name, fallback_used."
    )

    try:
        validated_resp, model_used = call_llm_structured(
            system_prompt, user_prompt, AIPatientSummaryResponse
        )
        validated_resp.patient_id = request.patient_id
        validated_resp.patient_name = p_name
        validated_resp.model_name = model_used
        validated_resp.fallback_used = False
        log_ai_event(db, f"AI patient summary: {p_name}", f"model={model_used}")
        return validated_resp
    except Exception as exc:
        logger.info("Using deterministic patient summary engine: %s", exc)

    # Deterministic Clinical Summary Synthesis
    # 1. Vitals Analysis
    v_analysis_parts = []
    bp_sys = latest_vitals.get("bp_systolic")
    bp_dia = latest_vitals.get("bp_diastolic")
    spo2 = latest_vitals.get("spo2")
    temp = latest_vitals.get("temperature_c")

    if bp_sys and bp_dia:
        if bp_sys >= 140 or bp_dia >= 90:
            v_analysis_parts.append(f"Elevated blood pressure ({bp_sys}/{bp_dia} mmHg) requires cardiovascular monitoring.")
        else:
            v_analysis_parts.append(f"Blood pressure ({bp_sys}/{bp_dia} mmHg) is within normal clinical limits.")
    if spo2:
        if spo2 < 92:
            v_analysis_parts.append(f"SpO2 of {spo2}% is significantly low, requiring immediate oxygenation assessment.")
        elif spo2 < 95:
            v_analysis_parts.append(f"SpO2 of {spo2}% is borderline low.")
        else:
            v_analysis_parts.append(f"Peripheral oxygen saturation ({spo2}%) is normal.")
    if temp:
        if temp >= 38.0:
            v_analysis_parts.append(f"Elevated body temperature ({temp}°C) indicates active pyrexia/infection.")
    if not v_analysis_parts:
        v_analysis_parts.append("No recent vital signs recorded; routine baseline check recommended.")
    vitals_analysis = " ".join(v_analysis_parts)

    # 2. Risk Level Stratification
    risk_level = "low"
    if (spo2 and spo2 < 92) or any("emergency" in c.lower() for c in active_concerns):
        risk_level = "critical"
    elif (bp_sys and bp_sys >= 150) or p_chronic.lower() not in ("none recorded", "none", ""):
        risk_level = "high" if (isinstance(p_age, int) and (p_age > 65 or p_age < 5)) else "moderate"

    # 3. Clinical Narrative
    history_items = [c.strip() for c in p_chronic.split(",") if c.strip() and c.strip().lower() != "none recorded"]
    narrative = (
        f"{p_name} is a {p_age}-year-old {p_sex} patient "
        f"with a medical history of {p_chronic}. "
        f"Current status reflects {risk_level} clinical risk. "
        f"{vitals_analysis} "
        f"Active prescriptions count: {len(med_list)}. "
        f"Recent medical encounters document {len(records)} visit records and {len(triages)} symptom triage checks."
    )

    # 4. Recommended Next Steps
    next_steps = [
        "Re-evaluate chronic illness control and review medication compliance.",
        "Perform updated comprehensive vital sign screening on next telemedicine visit.",
    ]
    if risk_level in ("high", "critical"):
        next_steps.insert(0, "Schedule priority tele-consultation with specialty physician within 48 hours.")
    if p_allergies and p_allergies.lower() != "none recorded":
        next_steps.append(f"Verify allergy bracelet and cross-check future prescriptions against documented allergy: {p_allergies}.")

    summary_resp = AIPatientSummaryResponse(
        patient_id=request.patient_id,
        patient_name=p_name,
        summary_narrative=narrative,
        key_medical_history=history_items or ["No significant chronic diseases on file"],
        active_concerns_and_symptoms=active_concerns[:4] or ["No active acute complaints reported"],
        allergies_and_contraindications=[p_allergies] if p_allergies.lower() != "none recorded" else ["No known drug allergies"],
        vitals_analysis=vitals_analysis,
        current_medications=med_list or ["No active pharmacotherapy"],
        recommended_clinical_next_steps=next_steps,
        risk_level=risk_level,
        model_name="deterministic_clinical_summary",
        fallback_used=True,
    )
    log_ai_event(db, f"AI patient summary: {p_name}", f"fallback=True; risk={risk_level}")
    return summary_resp


# ─────────────────────────────────────────────────────────────────────────────
# 3. Doctor Note Drafting Workflow (SOAP)
# ─────────────────────────────────────────────────────────────────────────────
def _match_standard_prescriptions(db: Session, complaint: str) -> list[AIPrescriptionSuggestion]:
    """Provide safe, evidence-based medication suggestions from India's essential formulary."""
    complaint_lower = complaint.lower()
    suggestions = []

    if any(k in complaint_lower for k in ("fever", "bukhar", "pyrexia", "body ache", "headache", "pain")):
        suggestions.append(
            AIPrescriptionSuggestion(
                medicine_name="Paracetamol",
                dosage="500 mg",
                frequency="1-0-1",
                duration_days=3,
                instructions="After meals; take with warm water as needed for fever or pain",
            )
        )
    if any(k in complaint_lower for k in ("cough", "khansi", "cold", "sneeze", "runny nose", "rhinitis")):
        suggestions.append(
            AIPrescriptionSuggestion(
                medicine_name="Cetirizine",
                dosage="10 mg",
                frequency="0-0-1",
                duration_days=5,
                instructions="At bedtime; may cause mild drowsiness",
            )
        )
    if any(k in complaint_lower for k in ("diarrhea", "loose motion", "dast", "vomit", "dehydration")):
        suggestions.append(
            AIPrescriptionSuggestion(
                medicine_name="Oral Rehydration Salts (ORS)",
                dosage="1 sachet in 1 liter clean water",
                frequency="Frequent sips",
                duration_days=3,
                instructions="Consume continuously after every loose stool",
            )
        )
        suggestions.append(
            AIPrescriptionSuggestion(
                medicine_name="Zinc Sulfate",
                dosage="20 mg",
                frequency="1-0-0",
                duration_days=10,
                instructions="Once daily after food to restore mucosal integrity",
            )
        )
    if any(k in complaint_lower for k in ("acidity", "gas", "gerd", "heartburn", "gastritis")):
        suggestions.append(
            AIPrescriptionSuggestion(
                medicine_name="Pantoprazole",
                dosage="40 mg",
                frequency="1-0-0",
                duration_days=7,
                instructions="Take 30 minutes before breakfast on an empty stomach",
            )
        )
    if any(k in complaint_lower for k in ("hypertension", "high bp", "bp high")):
        suggestions.append(
            AIPrescriptionSuggestion(
                medicine_name="Amlodipine",
                dosage="5 mg",
                frequency="1-0-0",
                duration_days=30,
                instructions="Take once daily in morning; monitor BP weekly",
            )
        )

    if not suggestions:
        suggestions.append(
            AIPrescriptionSuggestion(
                medicine_name="Paracetamol",
                dosage="500 mg",
                frequency="SOS (as needed)",
                duration_days=3,
                instructions="Take with water if body ache or fever develops",
            )
        )
    return suggestions


def draft_doctor_notes_ai(
    db: Session,
    request: AIDoctorNoteDraftRequest,
    caller: Optional[User] = None
) -> AIDoctorNoteDraftResponse:
    """
    Drafts an official structured clinical SOAP note, electronic prescriptions,
    and patient-friendly instructions from rough dictation or consultation data.
    """
    patient: Optional[Patient] = None
    if request.patient_id:
        patient = db.get(Patient, request.patient_id)

    patient_ctx = ""
    if patient:
        patient_ctx = (
            f"Patient: {patient.name}, Age: {patient.age}, Sex: {patient.sex}. "
            f"Known Conditions: {patient.chronic_conditions or 'None'}. Allergies: {patient.allergies or 'None'}."
        )

    # Format vitals string
    vitals_repr = "Not recorded"
    if request.vitals:
        vitals_repr = ", ".join(f"{k}: {v}" for k, v in request.vitals.items())

    # Attempt LLM Note Drafting
    system_prompt = (
        "You are an expert physician documenting a clinical consultation. "
        "Structure the encounter into an accredited SOAP format (Subjective, Objective, Assessment, Plan). "
        "Formulate accurate prescriptions adhering to standard dosing schedules (e.g. '1-0-1' for morning-noon-night). "
        "Write clear, empathetic patient discharge instructions in plain language. "
        "Return ONLY a valid JSON object matching the requested schema."
    )
    user_prompt = (
        f"Clinical Encounter Details:\n"
        f"- Patient Profile: {patient_ctx or 'Outpatient encounter'}\n"
        f"- Chief Complaint: {request.chief_complaint}\n"
        f"- Symptoms & Timeline: {request.symptoms_and_history or 'None provided'} (Duration: {request.duration or 'Not specified'})\n"
        f"- Vitals: {vitals_repr}\n"
        f"- Physical Examination: {request.physical_examination or 'Standard tele-consult inspection'}\n"
        f"- Raw Doctor Notes / Dictation: {request.raw_dictation_or_notes or 'None'}\n"
        f"- Suspected Impression: {request.clinical_impression or 'Clinical evaluation required'}\n"
        f"- Language: {request.language}\n\n"
        "Generate a complete JSON note with fields: chief_complaint, soap_note (subjective, objective, assessment, plan), "
        "suggested_prescriptions, patient_instructions, follow_up_recommendation, e_prescription_ready, summary, model_name, fallback_used."
    )

    try:
        validated_resp, model_used = call_llm_structured(
            system_prompt, user_prompt, AIDoctorNoteDraftResponse
        )
        validated_resp.model_name = model_used
        validated_resp.fallback_used = False
        log_ai_event(db, f"AI doctor note: {request.chief_complaint}", f"model={model_used}")
        return validated_resp
    except Exception as exc:
        logger.info("Using deterministic doctor note drafting engine: %s", exc)

    # Deterministic SOAP Engine Execution
    # 1. Subjective
    subj_parts = [
        f"Patient presents with chief complaint of {request.chief_complaint}."
    ]
    if request.duration:
        subj_parts.append(f"Symptoms have persisted for approximately {request.duration}.")
    if request.symptoms_and_history:
        subj_parts.append(f"History of present illness: {request.symptoms_and_history}.")
    if request.raw_dictation_or_notes:
        subj_parts.append(f"Consultation notes: {request.raw_dictation_or_notes}.")
    subjective_text = " ".join(subj_parts)

    # 2. Objective
    obj_parts = [f"Vital Signs: {vitals_repr}."]
    if request.physical_examination:
        obj_parts.append(f"Examination Findings: {request.physical_examination}.")
    else:
        obj_parts.append("General examination: Conscious, alert, oriented in time and space, no acute distress observed.")
    objective_text = " ".join(obj_parts)

    # 3. Assessment
    assessment_text = (
        request.clinical_impression.strip()
        if request.clinical_impression
        else f"Clinical evaluation of {request.chief_complaint}. Findings consistent with acute symptomatic presentation; rule out secondary bacterial etiology."
    )

    # 4. Prescriptions
    prescriptions = _match_standard_prescriptions(db, f"{request.chief_complaint} {request.symptoms_and_history}")

    # 5. Plan
    med_summary = "; ".join(f"{p.medicine_name} {p.dosage} ({p.frequency}) for {p.duration_days}d" for p in prescriptions)
    plan_text = (
        f"1. Pharmacotherapy: {med_summary}.\n"
        f"2. Supportive measures: Adequate oral hydration, balanced diet, and complete rest.\n"
        f"3. Monitoring: Observe for red flag symptoms (SpO2 drop, dyspnea, persistent high fever).\n"
        f"4. Electronic prescription generated for local pharmacy reservation."
    )

    # 6. Patient Instructions & Follow up
    patient_instructions = (
        f"Please take your prescribed medicines on time after meals as instructed. "
        f"Drink plenty of boiled water and get sufficient rest. "
        f"If you develop severe breathlessness, chest pain, or your fever does not subside in 3 days, "
        f"visit the nearest community health center or hospital immediately."
    )
    follow_up = "Follow up in 3 to 5 days if symptoms do not improve, or immediately in case of emergency."

    note_resp = AIDoctorNoteDraftResponse(
        chief_complaint=request.chief_complaint,
        soap_note=SOAPNote(
            subjective=subjective_text,
            objective=objective_text,
            assessment=assessment_text,
            plan=plan_text,
        ),
        suggested_prescriptions=prescriptions,
        patient_instructions=patient_instructions,
        follow_up_recommendation=follow_up,
        e_prescription_ready=True,
        summary=f"SOAP note drafted for {request.chief_complaint} ({len(prescriptions)} medications prescribed).",
        model_name="deterministic_soap_engine",
        fallback_used=True,
    )
    log_ai_event(db, f"AI doctor note: {request.chief_complaint}", "fallback=True")
    return note_resp


# ─────────────────────────────────────────────────────────────────────────────
# 4. Service Health & Diagnostics
# ─────────────────────────────────────────────────────────────────────────────
def get_ai_service_status() -> AIHealthStatusOut:
    """Returns AI service health, configured models, and fallback readiness."""
    provider, key, model = get_active_llm_provider()
    return AIHealthStatusOut(
        status="ok",
        configured_provider=provider,
        model=model,
        has_api_key=bool(key),
        timeout_seconds=settings.LLM_TIMEOUT_SECONDS,
        fallback_engine_ready=True,
        supported_workflows=["medical_triage", "patient_summary", "doctor_note_drafting"],
    )
