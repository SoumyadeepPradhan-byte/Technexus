"""
app/ai/matching.py  –  DOCTOR MATCHING: connect the patient to the right available doctor.

v0 = weighted score. Upgrade path: learn weights from consultation outcomes / no-show rates.
"""


def rank_doctors(doctors: list[dict], specialty: str, language: str, region_id: int | None,
                 urgency: str = "routine") -> list[dict]:
    """
    doctors: [{id, specialty, languages: [..], is_online, region_id, open_capacity, total_consultations}]
    returns the same list, sorted best-first, each with 'match_score' and 'match_reasons'
    """
    out = []
    for d in doctors:
        score, reasons = 0.0, []
        if d["specialty"] == specialty:
            score += 3; reasons.append("specialty match")
        elif d["specialty"] == "general_medicine":
            score += 1.5; reasons.append("general physician")
        if language in d["languages"]:
            score += 2; reasons.append(f"speaks {language}")
        if d["is_online"]:
            score += 2 if urgency in ("urgent", "emergency") else 1; reasons.append("online now")
        if region_id and d.get("region_id") == region_id:
            score += 1; reasons.append("same district")
        if d["open_capacity"] > 0:
            score += min(1.0, d["open_capacity"] / 5); reasons.append(f"{d['open_capacity']} slots free")
        else:
            score -= 5
        out.append({**d, "match_score": round(score, 2), "match_reasons": reasons})
    return sorted(out, key=lambda x: -x["match_score"])
