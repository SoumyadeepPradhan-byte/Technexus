"""
app/ai/language.py  –  MULTILINGUAL: understand symptoms in any language, answer in the user's language.

v0 = dictionaries. Covers English, Hindi (Devanagari + roman "Hinglish"), Odia (script + roman).
Upgrade path: an LLM or IndicTrans2 for translation; a small classifier / embedding search for symptom
normalization so "pet me mrod" still maps to abdominal_pain.
"""
import re

# canonical symptom code → words people actually type/say (lowercase). Add languages freely.
SYMPTOM_ALIASES = {
    "fever": ["fever", "bukhar", "bukhaar", "jwar", "jwara", "बुखार", "ज्वर", "ଜ୍ୱର", "jara", "taap"],
    "cough": ["cough", "khansi", "khasi", "kasha", "खांसी", "ଖାସି", "kaash"],
    "cold": ["cold", "sardi", "jukam", "zukam", "सर्दी", "जुकाम", "ଥଣ୍ଡା", "thanda", "runny nose"],
    "breathlessness": ["breathless", "shortness of breath", "difficulty breathing", "saans", "sans", "dam", "shwas",
                       "सांस", "साँस लेने में", "ଶ୍ୱାସ", "swasa", "breathing problem", "can't breathe"],
    "chest_pain": ["chest pain", "chhati dard", "seene me dard", "seena", "छाती", "सीने में दर्द", "ଛାତି", "chati"],
    "abdominal_pain": ["stomach pain", "abdominal pain", "pet dard", "pet me dard", "पेट दर्द", "ପେଟ", "peta"],
    "vomiting": ["vomit", "vomiting", "ulti", "उल्टी", "ବାନ୍ତି", "banti"],
    "diarrhea": ["diarrhea", "diarrhoea", "loose motion", "dast", "patla", "दस्त", "ଝାଡ଼ା", "jhada"],
    "headache": ["headache", "sir dard", "sar dard", "sirdard", "सिर दर्द", "ମୁଣ୍ଡ", "munda", "matha"],
    "dizziness": ["dizzy", "dizziness", "chakkar", "चक्कर", "ମୁଣ୍ଡ ବୁଲାଉଛି", "bulauchi"],
    "unconscious": ["unconscious", "fainted", "behosh", "बेहोश", "ଅଚେତ", "acheta", "passed out"],
    "seizure": ["seizure", "fits", "daura", "mirgi", "दौरा", "मिर्गी", "ମୂର୍ଚ୍ଛା", "convulsion"],
    "bleeding": ["bleeding", "blood", "khoon", "khun", "खून", "ରକ୍ତ", "rakta"],
    "snake_bite": ["snake", "snake bite", "saanp", "sanp", "सांप", "ସାପ", "sapa"],
    "weakness": ["weakness", "kamjori", "kamzori", "कमजोरी", "ଦୁର୍ବଳ", "durbala", "tired", "thakan"],
    "rash": ["rash", "daane", "dane", "khujli", "itching", "दाने", "खुजली", "ଚର୍ମ", "skin"],
    "body_ache": ["body ache", "badan dard", "body pain", "बदन दर्द", "ଦେହ ବିନ୍ଧା", "joint pain", "jod dard"],
    "injury": ["injury", "fall", "fracture", "chot", "gir gaya", "चोट", "ଆଘାତ", "aghata", "cut", "burn", "jala"],
    "eye_problem": ["eye", "aankh", "आंख", "ଆଖି", "akhi", "vision"],
    "pregnancy_issue": ["pregnant", "pregnancy", "garbh", "गर्भ", "ଗର୍ଭ", "labour pain", "delivery"],
    "urinary": ["urine", "peshab", "पेशाब", "ପରିସ୍ରା", "burning urination"],
    "mental_health": ["sad", "depressed", "suicide", "khudkushi", "आत्महत्या", "anxiety", "tension", "sleep problem"],
    "ear_throat": ["ear", "kaan", "कान", "throat", "gala", "गला", "ଗଳା"],
    "high_fever": ["high fever", "tez bukhar", "bahut bukhar", "तेज बुखार", "104"],
    "blood_in_stool_urine": ["blood in stool", "blood in urine", "khoon aana", "kala dast", "black stool"],
    "stiff_neck": ["stiff neck", "gardan akad", "गर्दन", "neck stiff"],
    "no_urine_child": ["no urine", "peshab nahi", "sunken eyes", "dry mouth"],
}

# UI / advice strings. Keys are stable; values per language. Add a language = add a column.
STRINGS = {
    "en": {
        "call_emergency": "This may be an emergency. Call {number} for an ambulance now, or go to the nearest hospital with emergency services immediately.",
        "see_doctor_today": "Please consult a doctor today. We have found an available doctor for you; a health worker will help you connect.",
        "book_soon": "You should talk to a doctor within the next 2-3 days. You can book a phone or video consultation - no need to travel.",
        "self_care": "This can usually be managed at home. Drink fluids and rest. If it gets worse, lasts more than 3 days, or you feel breathless, contact a doctor.",
        "not_reassured": "Even if symptoms seem mild, {reason}. Please speak to a doctor.",
        "disclaimer": "This is guidance, not a diagnosis. When in doubt, talk to a doctor.",
        "appointment_confirmed": "Appointment confirmed with Dr {doctor} at {time}. Mode: {mode}. You do not need to travel.",
        "medicine_reserved": "Your medicine {medicine} is reserved at {pharmacy}, {village}. Collect before {until}. Reservation #{id}.",
        "medicine_unavailable": "{medicine} is not in stock at nearby pharmacies today. We will notify you when it arrives - please do not travel yet.",
        "emergency_escalated": "Emergency reported for {patient}. Nearest hospital with emergency care: {hospital} ({phone}).",
        "child_under_5": "children under 5 can get worse quickly",
        "age_over_65": "people over 65 need extra care",
        "pregnancy": "in pregnancy even small symptoms matter",
    },
    "hi": {
        "call_emergency": "यह आपातकाल हो सकता है। अभी {number} पर एम्बुलेंस के लिए कॉल करें, या तुरंत नज़दीकी आपातकालीन अस्पताल जाएँ।",
        "see_doctor_today": "कृपया आज ही डॉक्टर से बात करें। हमने आपके लिए एक उपलब्ध डॉक्टर ढूँढ लिया है; स्वास्थ्य कार्यकर्ता आपको जोड़ने में मदद करेंगे।",
        "book_soon": "अगले 2-3 दिनों में डॉक्टर से बात करें। आप फ़ोन या वीडियो पर परामर्श बुक कर सकते हैं - यात्रा की ज़रूरत नहीं।",
        "self_care": "यह आमतौर पर घर पर ठीक हो जाता है। पानी पिएँ और आराम करें। अगर बढ़े, 3 दिन से ज़्यादा रहे, या साँस फूले तो डॉक्टर से संपर्क करें।",
        "not_reassured": "लक्षण हल्के लगें तब भी, {reason}। कृपया डॉक्टर से बात करें।",
        "disclaimer": "यह मार्गदर्शन है, निदान नहीं। संदेह हो तो डॉक्टर से बात करें।",
        "appointment_confirmed": "डॉ {doctor} के साथ {time} पर अपॉइंटमेंट पक्का। माध्यम: {mode}। आपको यात्रा नहीं करनी है।",
        "medicine_reserved": "आपकी दवा {medicine} {pharmacy}, {village} में आरक्षित है। {until} से पहले ले लें। आरक्षण #{id}।",
        "medicine_unavailable": "{medicine} आज पास की दुकानों में उपलब्ध नहीं है। आने पर हम सूचित करेंगे - अभी यात्रा न करें।",
        "emergency_escalated": "{patient} के लिए आपातकाल दर्ज। नज़दीकी आपातकालीन अस्पताल: {hospital} ({phone})।",
        "child_under_5": "5 साल से छोटे बच्चों की हालत जल्दी बिगड़ सकती है",
        "age_over_65": "65 से ऊपर के लोगों को अतिरिक्त देखभाल चाहिए",
        "pregnancy": "गर्भावस्था में छोटे लक्षण भी महत्वपूर्ण हैं",
    },
    "or": {
        "call_emergency": "ଏହା ଜରୁରୀକାଳୀନ ହୋଇପାରେ। ଏବେ {number} କୁ ଆମ୍ବୁଲାନ୍ସ ପାଇଁ କଲ କରନ୍ତୁ, କିମ୍ବା ତୁରନ୍ତ ନିକଟସ୍ଥ ଜରୁରୀ ସେବା ଥିବା ହସ୍ପିଟାଲକୁ ଯାଆନ୍ତୁ।",
        "see_doctor_today": "ଦୟାକରି ଆଜି ଡାକ୍ତରଙ୍କ ସହ କଥା ହୁଅନ୍ତୁ। ଆମେ ଆପଣଙ୍କ ପାଇଁ ଜଣେ ଉପଲବ୍ଧ ଡାକ୍ତର ପାଇଛୁ; ସ୍ୱାସ୍ଥ୍ୟ କର୍ମୀ ଆପଣଙ୍କୁ ଯୋଡ଼ିବେ।",
        "book_soon": "ଆଗାମୀ 2-3 ଦିନ ମଧ୍ୟରେ ଡାକ୍ତରଙ୍କ ସହ କଥା ହୁଅନ୍ତୁ। ଫୋନ କିମ୍ବା ଭିଡିଓରେ ପରାମର୍ଶ ବୁକ୍ କରିପାରିବେ - ଯାତ୍ରା ଦରକାର ନାହିଁ।",
        "self_care": "ଏହା ସାଧାରଣତଃ ଘରେ ଠିକ୍ ହୋଇଯାଏ। ପାଣି ପିଅନ୍ତୁ ଓ ବିଶ୍ରାମ ନିଅନ୍ତୁ। ଯଦି ବଢ଼େ, 3 ଦିନରୁ ଅଧିକ ରହେ, କିମ୍ବା ଶ୍ୱାସ କଷ୍ଟ ହୁଏ ତେବେ ଡାକ୍ତରଙ୍କୁ ଯୋଗାଯୋଗ କରନ୍ତୁ।",
        "not_reassured": "ଲକ୍ଷଣ ହାଲୁକା ଲାଗିଲେ ମଧ୍ୟ, {reason}। ଦୟାକରି ଡାକ୍ତରଙ୍କ ସହ କଥା ହୁଅନ୍ତୁ।",
        "disclaimer": "ଏହା ମାର୍ଗଦର୍ଶନ, ନିଦାନ ନୁହେଁ। ସନ୍ଦେହ ଥିଲେ ଡାକ୍ତରଙ୍କ ସହ କଥା ହୁଅନ୍ତୁ।",
        "appointment_confirmed": "ଡାକ୍ତର {doctor}ଙ୍କ ସହ {time}ରେ ଅପଏଣ୍ଟମେଣ୍ଟ ନିଶ୍ଚିତ। ମାଧ୍ୟମ: {mode}। ଆପଣଙ୍କୁ ଯାତ୍ରା କରିବାକୁ ପଡ଼ିବ ନାହିଁ।",
        "medicine_reserved": "ଆପଣଙ୍କ ଔଷଧ {medicine} {pharmacy}, {village}ରେ ସଂରକ୍ଷିତ। {until} ପୂର୍ବରୁ ନିଅନ୍ତୁ। ସଂରକ୍ଷଣ #{id}।",
        "medicine_unavailable": "{medicine} ଆଜି ନିକଟସ୍ଥ ଔଷଧାଳୟରେ ନାହିଁ। ଆସିଲେ ଆମେ ଜଣାଇବୁ - ଏବେ ଯାତ୍ରା କରନ୍ତୁ ନାହିଁ।",
        "emergency_escalated": "{patient}ଙ୍କ ପାଇଁ ଜରୁରୀକାଳୀନ ଦାଖଲ। ନିକଟସ୍ଥ ଜରୁରୀ ସେବା ହସ୍ପିଟାଲ: {hospital} ({phone})।",
        "child_under_5": "5 ବର୍ଷରୁ ଛୋଟ ପିଲାଙ୍କ ଅବସ୍ଥା ଶୀଘ୍ର ଖରାପ ହୋଇପାରେ",
        "age_over_65": "65 ବର୍ଷରୁ ଅଧିକ ଲୋକଙ୍କୁ ଅତିରିକ୍ତ ଯତ୍ନ ଦରକାର",
        "pregnancy": "ଗର୍ଭାବସ୍ଥାରେ ଛୋଟ ଲକ୍ଷଣ ମଧ୍ୟ ଗୁରୁତ୍ୱପୂର୍ଣ୍ଣ",
    },
}


def normalize_symptoms(text_or_list) -> list[str]:
    """
    Input:  "bukhar aur khansi 3 din se"   or   ["fever", "ଖାସି"]   (any language, any spelling)
    Output: ["fever", "cough"]   – canonical codes the triage rules understand
    """
    items = text_or_list if isinstance(text_or_list, list) else re.split(r"[,;/\n]|\baur\b|\band\b|\bo\b", str(text_or_list))
    found: list[str] = []
    for raw in items:
        t = raw.strip().lower()
        if not t:
            continue
        for code, aliases in SYMPTOM_ALIASES.items():
            if any(a in t for a in aliases) and code not in found:
                found.append(code)
    # high fever implies fever
    if "high_fever" in found and "fever" not in found:
        found.append("fever")
    return found


def translate(key: str, lang: str, **kwargs) -> str:
    """Return a UI/advice string in `lang` (falls back to English). Placeholders are filled from kwargs."""
    table = STRINGS.get(lang) or STRINGS["en"]
    template = table.get(key) or STRINGS["en"].get(key) or key
    try:
        return template.format(**kwargs)
    except KeyError:
        return template


def supported_languages() -> list[dict]:
    names = {"en": "English", "hi": "हिन्दी (Hindi)", "or": "ଓଡ଼ିଆ (Odia)"}
    return [{"code": c, "name": names.get(c, c)} for c in STRINGS]
