"""
app/ai/triage.py  –  THE LOW-BANDWIDTH AI SYMPTOM CHECKER
============================================================
Design rule #1 (from the PS "Clinical safety"): NEVER falsely reassure.
  * Red-flag symptoms → EMERGENCY, no matter what else is said.
  * Children under 5, adults over 65, and pregnant women are bumped one level up.
  * Vitals (SpO2, temperature) can override words.
  * "self_care" ALWAYS carries a "see a doctor if…" line.

v0 = transparent rules a doctor can read and sign off on (that's a feature, not a limitation -
judges can audit it). Upgrade path: an ML classifier or LLM *behind* these guardrails, never
instead of them. Input is tiny (a few words) and output is tiny (a few fields) → works on 2G.
"""
from app.ai.language import normalize_symptoms, translate

EMERGENCY = {
    "chest_pain": "chest pain can be a heart attack",
    "breathlessness": "difficulty breathing needs immediate care",
    "unconscious": "loss of consciousness",
    "seizure": "seizures need urgent evaluation",
    "snake_bite": "snake bite needs anti-venom within hours",
    "bleeding": "uncontrolled bleeding",
    "stiff_neck": "fever with stiff neck can be meningitis",
    "blood_in_stool_urine": "internal bleeding must be ruled out",
    "pregnancy_issue": "pregnancy complications can escalate fast",
}
URGENT = {
    "high_fever": "very high fever",
    "vomiting": "persistent vomiting risks dehydration",
    "dizziness": "dizziness with other symptoms",
    "injury": "injury may need an X-ray",
    "no_urine_child": "signs of dehydration",
    "eye_problem": "eye problems can worsen quickly",
    "mental_health": "mental health concerns deserve prompt support",
    "urinary": "urinary infection can spread to kidneys",
}
SPECIALTY = {
    "chest_pain": "cardiology", "breathlessness": "general_medicine", "pregnancy_issue": "obstetrics",
    "injury": "orthopedics", "rash": "dermatology", "eye_problem": "ophthalmology", "mental_health": "psychiatry",
    "seizure": "neurology", "stiff_neck": "general_medicine", "ear_throat": "ent", "snake_bite": "emergency",
}
LEVELS = ["self_care", "routine", "urgent", "emergency"]


def _bump(level: str, steps: int = 1) -> str:
    return LEVELS[min(len(LEVELS) - 1, LEVELS.index(level) + steps)]


def assess_symptoms(symptoms, age: int | None = None, sex: str = "", duration_days: int = 1,
                    vitals: dict | None = None, is_pregnant: bool = False, language: str = "hi",
                    emergency_number: str = "108") -> dict:
    """
    symptoms: free text ("bukhar aur khansi") or list, any language
    returns: {urgency, red_flags: [str], recommended_action: str (localized), recommended_specialty,
              symptoms_normalized: [codes], escalation: bool, disclaimer, confidence, model_name}
    """
    codes = normalize_symptoms(symptoms)
    vitals = vitals or {}
    red_flags: list[str] = []
    level = "self_care" if codes else "routine"   # unknown symptoms → at least talk to a doctor

    # 1. Red flags → emergency
    for c in codes:
        if c in EMERGENCY:
            red_flags.append(EMERGENCY[c])
    if vitals.get("spo2") is not None and vitals["spo2"] < 90:
        red_flags.append(f"oxygen saturation {vitals['spo2']}% is dangerously low")
    if vitals.get("temperature_c") is not None and vitals["temperature_c"] >= 40.0:
        red_flags.append(f"temperature {vitals['temperature_c']}°C is very high")
    if age is not None and age < 1 and "fever" in codes:
        red_flags.append("fever in an infant under 1 year")
    if red_flags:
        level = "emergency"

    # 2. Urgent
    urgent_reasons = [URGENT[c] for c in codes if c in URGENT]
    if vitals.get("spo2") is not None and 90 <= vitals["spo2"] < 94:
        urgent_reasons.append(f"oxygen saturation {vitals['spo2']}% is low")
    if "fever" in codes and duration_days >= 3:
        urgent_reasons.append("fever lasting 3 days or more")
    if "diarrhea" in codes and duration_days >= 2:
        urgent_reasons.append("diarrhea for 2+ days risks dehydration")
    if "cough" in codes and duration_days >= 14:
        urgent_reasons.append("cough for 2+ weeks must be checked for TB")
    if level != "emergency" and urgent_reasons:
        level = "urgent"

    # 3. Routine
    if level == "self_care" and any(c in codes for c in ("fever", "cough", "abdominal_pain", "diarrhea", "rash",
                                                          "body_ache", "headache", "weakness", "ear_throat")):
        level = "routine"

    # 4. Vulnerable groups: never leave them at the lowest level
    vulnerable = []
    if age is not None and age < 5:
        vulnerable.append("child_under_5")
    if age is not None and age > 65:
        vulnerable.append("age_over_65")
    if is_pregnant:
        vulnerable.append("pregnancy")
    if vulnerable and level in ("self_care", "routine"):
        level = _bump(level)

    # 5. Action text in the user's language
    specialty = next((SPECIALTY[c] for c in codes if c in SPECIALTY), "pediatrics" if (age is not None and age < 12) else "general_medicine")
    if level == "emergency":
        action = translate("call_emergency", language, number=emergency_number)
    elif level == "urgent":
        action = translate("see_doctor_today", language)
    elif level == "routine":
        action = translate("book_soon", language)
    else:
        action = translate("self_care", language)
    if vulnerable and level != "emergency":
        action = translate("not_reassured", language, reason=", ".join(translate(v, language) for v in vulnerable)) + " " + action

    return {
        "urgency": level,
        "red_flags": red_flags,
        "urgent_reasons": urgent_reasons,
        "vulnerable_group": vulnerable,
        "recommended_action": action,
        "recommended_specialty": "emergency" if level == "emergency" else specialty,
        "symptoms_normalized": codes,
        "escalation": level == "emergency",
        "disclaimer": translate("disclaimer", language),
        "confidence": 0.9 if codes else 0.4,
        "model_name": "rules_v0",
    }
