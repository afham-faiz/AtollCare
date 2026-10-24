# F-M2.2 fallback — keyword rules used when Gemini is unavailable (mock mode, timeout, invalid output).
from __future__ import annotations

import re
from datetime import datetime, timedelta

from app.models import Intake, SuspectedCondition

RULES: list[tuple[str, list[str], list[tuple[str, str]]]] = [
    # (condition_id, keyword patterns, [(red-flag pattern, label)])
    (
        "stemi",
        [r"chest pain", r"crushing", r"left arm", r"sweat", r"tight(ness)? (in|of) (the )?chest", r"jaw pain"],
        [(r"crushing", "crushing chest pain"), (r"left arm", "radiation to left arm"), (r"sweat", "sweating")],
    ),
    (
        "stroke",
        [r"weak(ness)?", r"slurred", r"face (is )?droop", r"drooping", r"can'?t speak", r"numb", r"one side"],
        [(r"slurred", "slurred speech"), (r"droop", "facial droop"), (r"weakness", "one-sided weakness")],
    ),
    (
        "major_trauma",
        [r"fell|fall from|fallen", r"fracture", r"bleeding heavily|heavy bleeding|bleeding a lot", r"accident",
         r"injur", r"wound", r"crash"],
        [(r"bleeding heavily|heavy bleeding|bleeding a lot", "heavy bleeding"), (r"open fracture", "open fracture"),
         (r"unconscious", "loss of consciousness"), (r"pale", "pale / shocked")],
    ),
    (
        "pph",
        [r"gave birth|delivered|after (the )?birth|postpartum", r"bleeding", r"soak"],
        [(r"bleeding heavily|soak", "heavy postpartum bleeding"), (r"dizzy", "dizziness")],
    ),
    (
        "sepsis",
        [r"fever", r"confus", r"infect", r"breathing fast", r"shiver|rigor"],
        [(r"confus", "new confusion"), (r"breathing fast", "fast breathing")],
    ),
    (
        "respiratory_failure",
        [r"can'?t breathe|cannot breathe|short(ness)? of breath|breathless", r"wheez", r"blue lips", r"asthma"],
        [(r"blue lips", "cyanosis"), (r"can'?t breathe|cannot breathe", "severe breathlessness")],
    ),
    ("appendicitis", [r"right lower|lower right", r"abdominal pain|stomach pain|belly pain", r"vomit"], []),
]

QUESTIONS = {
    "stemi": ["Any allergy to aspirin?", "Exact time the pain started?", "Any history of heart disease?"],
    "stroke": ["When was the patient last seen well?", "Is the patient on blood thinners?", "Blood glucose?"],
    "major_trauma": ["Mechanism and time of injury?", "Estimated blood loss?", "Any head injury or loss of consciousness?"],
    "pph": ["Time of delivery?", "Estimated blood loss?", "Is the placenta delivered?"],
    "sepsis": ["Source of infection?", "Any allergies to antibiotics?", "Urine output today?"],
    "respiratory_failure": ["Known asthma or COPD?", "SpO₂ reading?", "Able to speak in full sentences?"],
    "appendicitis": ["Where exactly is the pain?", "Any fever or vomiting?", "Last meal?"],
    "other": ["When did symptoms start?", "Any known medical conditions?", "Any medications or allergies?"],
}

COMPLAINTS = {
    "stemi": "Chest pain",
    "stroke": "Sudden one-sided weakness / speech difficulty",
    "major_trauma": "Traumatic injury with bleeding",
    "pph": "Bleeding after childbirth",
    "sepsis": "Fever with confusion",
    "respiratory_failure": "Breathing difficulty",
    "appendicitis": "Abdominal pain",
    "other": "Unwell — undifferentiated",
}

_NUM_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "half an": 0.5, "ten": 10,
              "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50}


def parse_onset(text: str, now: datetime) -> tuple[datetime | None, str]:
    t = text.lower()
    pattern = r"(\d+(?:\.\d+)?|half an|an|a|one|two|three|four|five|ten|twenty|thirty|forty|fifty)\s*(minutes?|mins?|hours?|hrs?|h)\b"
    m = re.search(pattern + r"\s*(ago|before)?", t)
    if not m:
        if "yesterday" in t:
            return now - timedelta(hours=18), "approx"
        return None, "unknown"
    raw, unit = m.group(1), m.group(2)
    value = float(raw) if raw[0].isdigit() else float(_NUM_WORDS.get(raw, 1))
    minutes = value * 60 if unit.startswith("h") else value
    exact = raw[0].isdigit() and "about" not in t[max(0, m.start() - 8): m.start()]
    return now - timedelta(minutes=minutes), "exact" if exact else "approx"


def extract(raw_text: str, now: datetime, language: str = "en") -> Intake:
    text = raw_text.lower()
    scores: list[tuple[str, int, list[str], list[str]]] = []
    for cid, keywords, flags in RULES:
        matches = [re.search(k, text) for k in keywords]
        hits = [m.group(0) for m in matches if m]
        flag_hits = [label for pattern, label in flags if re.search(pattern, text)]
        if hits:
            scores.append((cid, len(hits), hits, flag_hits))
    scores.sort(key=lambda s: s[1], reverse=True)
    suspected: list[SuspectedCondition] = []
    red_flags: list[str] = []
    symptoms: list[str] = []
    remaining = 0.95
    for i, (cid, count, hits, flag_hits) in enumerate(scores[:3]):
        prob = min(0.85, 0.3 + 0.15 * count) if i == 0 else min(0.25, 0.08 * count)
        prob = round(min(prob, remaining), 2)
        remaining -= prob
        suspected.append(SuspectedCondition(condition_id=cid, probability=prob, rationale=f"Keywords: {', '.join(hits)}"))
        if i == 0:
            red_flags += flag_hits
        symptoms += hits
    primary = scores[0][0] if scores else "other"
    if not suspected:
        suspected.append(SuspectedCondition(condition_id="other", probability=0.5, rationale="No rule matched"))
    onset, confidence = parse_onset(raw_text, now)
    return Intake(
        raw_text=raw_text,
        language=language,
        chief_complaint=COMPLAINTS[primary],
        # symptoms already covered by a red-flag phrase are not repeated
        symptoms=[x for x in dict.fromkeys(symptoms) if not any(x in f for f in red_flags)][:8],
        red_flags=list(dict.fromkeys(red_flags)),
        onset_time=onset,
        onset_confidence=confidence,  # type: ignore[arg-type]
        suspected_conditions=suspected,
        missing_info=QUESTIONS[primary],
        extracted_by="fallback_rules",
    )
