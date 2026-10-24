# SBAR briefing for the receiving team: inputs for Gemini (hashed for caching) and the deterministic template fallback.
# Also the rule-based extraction of interventions / observations from crew notes.
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from app.core.clock import fmt_local
from app.core.news2 import partial_label
from app.models import Briefing, Extraction, Transfer

SUSPECTED = [
    ("Suspected STEMI / acute coronary syndrome", r"chest pain|crushing chest|st elevation|stemi"),
    ("Suspected stroke", r"slurred|facial droop|face.*droop|one.sided weakness|weakness of the (left|right)|stroke"),
    ("Major trauma / haemorrhage", r"fell|fall from|fracture|bleeding heavily|heavy bleeding|crash|stab"),
    ("Postpartum haemorrhage", r"gave birth|postpartum|after (the )?birth"),
    ("Suspected sepsis", r"fever.*confus|sepsis|infect"),
    ("Respiratory distress", r"can'?t breathe|short(ness)? of breath|wheez|asthma"),
]

VITAL_LABELS = [
    ("heart_rate", "HR"), ("resp_rate", "RR"), ("spo2", "SpO₂"), ("systolic_bp", "SBP"), ("temperature_c", "T"),
    ("consciousness", "ACVPU"),
]


def suspected_condition(text: str) -> str | None:
    t = text.lower()
    return next((label for label, pattern in SUSPECTED if re.search(pattern, t)), None)


def _fmt(v: Any) -> str:
    if isinstance(v, bool):
        return "on O₂" if v else "air"
    if isinstance(v, float):
        return f"{v:g}"
    return str(v)


def inputs(t: Transfer, origin: str, destination: str, mode_label: str, tz: str) -> dict[str, Any]:
    """Everything the briefing may use — and nothing else (Gemini must not invent values)."""
    return {
        "patient": t.patient.model_dump(exclude={"label"}),
        "complaint": t.complaint,
        "from": origin,
        "to": destination,
        "transport": mode_label,
        "eta_local": fmt_local(t.eta, tz),
        "latest_vitals": {k: {"value": _fmt(v.value), "source": v.source.value, "flag": v.flag} for k, v in t.latest.items()},
        "news2": {"total": t.news2.total, "band": t.news2.band, "complete": t.news2.complete} if t.news2 else None,
        "active_alerts": [a.text for a in t.alerts],
        "interventions": [f"{fmt_local(i.at, tz)} {i.text}" for i in t.interventions],
        "crew_notes": [f"{fmt_local(n.at, tz)} {n.text}" for n in t.notes
                       if n.author.value == "crew" and n.kind.value in ("voice", "text", "answer")][-8:],
        "hospital_questions": [
            {"q": n.text, "answered": any(m.reply_to == n.id for m in t.notes)} for n in t.notes if n.kind.value == "question"
        ],
    }


def inputs_hash(data: dict[str, Any]) -> str:
    # round vitals so a 1-bpm wobble doesn't trigger a new Gemini call
    slim = json.loads(json.dumps(data, default=str))
    for v in (slim.get("latest_vitals") or {}).values():
        try:
            v["value"] = str(round(float(v["value"]) / 5) * 5)
        except (TypeError, ValueError):
            pass
    return hashlib.sha256(json.dumps(slim, sort_keys=True).encode()).hexdigest()[:16]


def template(t: Transfer, data: dict[str, Any], now: datetime) -> Briefing:
    p = t.patient
    who = " ".join(x for x in [f"{p.age}y" if p.age else None, p.sex] if x) or "Patient"
    suspected = suspected_condition(" ".join([t.complaint, *[n.text for n in t.notes]]))
    n2 = t.news2
    n2_txt = "NEWS2 not yet available"
    if n2 and n2.total is not None:
        n2_txt = f"NEWS2 {n2.total} ({(n2.band or '').replace('_', '-')})" + ("" if n2.complete else f", {partial_label(n2).lower()}")
    vitals = ", ".join(f"{lbl} {data['latest_vitals'][k]['value']}" for k, lbl in VITAL_LABELS if k in data["latest_vitals"])
    situation = f"{who} from {data['from']} by {data['transport'].lower()}, ETA {data['eta_local']}. {t.complaint.rstrip('.')}."
    background_parts = [n for n in data["crew_notes"]][-2:]
    background = "Crew notes: " + " · ".join(background_parts) if background_parts else "No crew notes yet."
    assessment = f"{suspected + '. ' if suspected else ''}{n2_txt}. Vitals: {vitals or 'not recorded'}."
    if t.alerts:
        assessment += " Alerts: " + "; ".join(a.text for a in t.alerts) + "."
    rec = []
    if t.interventions:
        given = [re.sub(r"^(gave|given|administered)\s+", "", i.text, flags=re.I) for i in t.interventions[-3:]]
        rec.append("Already given: " + "; ".join(given) + ".")
    if suspected and "STEMI" in suspected:
        rec.append("Consider cath lab activation on arrival.")
    elif suspected and "stroke" in suspected.lower():
        rec.append("Consider stroke team + CT on arrival; confirm last-seen-well time.")
    elif suspected and "trauma" in suspected.lower():
        rec.append("Consider trauma team + blood on arrival.")
    rec.append(f"Prepare to receive at {data['to']}.")
    return Briefing(
        situation=situation, background=background, assessment=assessment, recommendation=" ".join(rec),
        suspected_condition=suspected, generated_by="template", generated_at=now,
    )


# ---------------------------------------------------------------- note extraction (fallback when Gemini is off)
INTERVENTION = re.compile(
    r"\b(gave|given|administered|started|applied|inserted|put on|commenced|nebuli[sz]ed)\b[^.;,]*",
    re.I,
)
DRUGS = re.compile(r"\b(aspirin|gtn|nitro\w*|morphine|oxygen|o2|adrenaline|salbutamol|txa|tranexamic acid|"
                   r"fluids?|saline|paracetamol|ondansetron|heparin|clopidogrel|ticagrelor)\b[^.;,]*", re.I)
OBSERVATION = re.compile(r"\b(pain [^.;,]*|sweat\w*|vomit\w*|pale|clammy|drowsy|confused|unresponsive|"
                         r"st elevation[^.;,]*|facial droop[^.;,]*|blood glucose [^.;,]*)", re.I)


def _cap(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:]


def extract(text: str) -> Extraction:
    interventions: list[str] = []
    for m in INTERVENTION.finditer(text):
        interventions.append(_cap(m.group(0)))
    if not interventions:
        interventions = [_cap(m.group(0)) for m in DRUGS.finditer(text)
                         if not re.search(r"\bnot on\b|\bno\b", text[max(0, m.start() - 8): m.start()], re.I)]
    observations = [_cap(m.group(0)) for m in OBSERVATION.finditer(text)]
    return Extraction(observations=list(dict.fromkeys(observations))[:6], interventions=list(dict.fromkeys(interventions))[:4])
