"""
app/ai/  –  THE AI/ML CONTRACT
================================
Every function here is PURE: plain dicts/lists in, plain dicts/lists out. No DB access.
The backend calls these; the AI/ML teammate replaces the internals with real models
WITHOUT touching any router. Keep the function signatures and return shapes stable.

    triage.py      assess_symptoms(...)      → urgency + red flags + action   (rules now → ML/LLM with guardrails later)
    language.py    normalize_symptoms(...)   → Hindi/Odia/English/typos → canonical codes
                   translate(...)            → UI/advice strings per language  (dictionary now → LLM later)
    bandwidth.py   recommend_mode(...)       → video / audio / text based on measured network
    matching.py    rank_doctors(...)         → best doctor for this patient (specialty, language, load)
"""
