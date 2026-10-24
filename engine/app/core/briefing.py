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
    def vital(k: str, lbl: str) -> str:
        v = data["latest_vitals"][k]
        return f"{lbl} {v['value']}" + (" (demo signal)" if v["source"] == "simulated" else "")

    vitals = ", ".join(vital(k, lbl) for k, lbl in VITAL_LABELS if k in data["latest_vitals"])
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
# Works clause by clause so "gave aspirin 300 mg and GTN spray, oxygen 4 litres" yields three items, not one.
CLAUSE = re.compile(r"\.(?!\d)|[;,]|\band\b|\bthen\b|\bplus\b", re.I)  # keeps "0.5 mg" whole
GIVEN = re.compile(r"\b(gave|given|administered|started|applied|inserted|put on|commenced|nebuli[sz]ed|splinted)\b\s*", re.I)
DRUG = re.compile(r"\b(aspirin|gtn|glyceryl trinitrate|nitro\w*|morphine|fentanyl|ketamine|methoxyflurane|penthrox|oxygen|o2|"
                  r"adrenaline|epinephrine|salbutamol|ipratropium|txa|tranexamic acid|iv fluids?|fluids?|saline|"
                  r"hartmann'?s|paracetamol|ondansetron|heparin|clopidogrel|ticagrelor|glucagon|glucose|naloxone|"
                  r"midazolam|amiodarone)\b", re.I)
PROCEDURE = re.compile(r"\b(iv access|cannula\w*|splint\w*|tourniquet|c-?collar|pelvic binder|traction|intubat\w*|"
                       r"defibrillat\w*|cpr|12-lead)\b", re.I)
DOSE = re.compile(r"\d+(\.\d+)?\s*(mg|mcg|micrograms?|g|ml|l|litres?|liters?|units?)\b|"
                  r"\b(spray|puffs?|nebuli[sz]er|neb|iv|im|io|sublingual|bolus|infusion)\b", re.I)
NOT_GIVEN = re.compile(r"\b(no|not|without|declined|refused|allergic|takes|taking|regular|usual|history)\b", re.I)
OBSERVATION = re.compile(r"\b(pain [^.;,]*|sweat\w*|vomit\w*|pale|clammy|drowsy|confused|unresponsive|"
                         r"st elevation[^.;,]*|facial droop[^.;,]*|blood glucose [^.;,]*)", re.I)


def _cap(s: str) -> str:
    s = s.strip()
    return s[:1].upper() + s[1:]


def _intervention(clause: str) -> str | None:
    thing = DRUG.search(clause) or PROCEDURE.search(clause)
    if not thing or NOT_GIVEN.search(clause[: thing.start()]):
        return None
    given = GIVEN.search(clause)
    # a drug named without a verb counts only with a dose or route ("oxygen 4 litres", "GTN spray")
    if not given and not PROCEDURE.search(clause) and not DOSE.search(clause[thing.end():]):
        return None
    item = clause[given.end():] if given and given.end() <= thing.start() else clause[thing.start():]
    return _cap(item.strip(" -")) or None


def extract(text: str) -> Extraction:
    interventions = [i for c in CLAUSE.split(text) if c and (i := _intervention(c))]
    observations = [_cap(m.group(0)) for m in OBSERVATION.finditer(text)]
    return Extraction(observations=list(dict.fromkeys(observations))[:6], interventions=list(dict.fromkeys(interventions))[:5])
