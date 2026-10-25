"""Vitals said out loud ("sats 94 on air, BP 120 over 80, temp 37.2, alert") read into numbers.

The camera measures heart and breathing rate only. SpO₂, blood pressure, temperature and ACVPU come from the crew's own
devices and eyes, and saying them is quicker than typing on a moving boat. Rule-based on purpose: every number has to
sit next to its name ("sats", "BP", "temp") and fall in a plausible range, or it is left out. A missed value costs
a tap; a wrong one would be scored."""
from __future__ import annotations

import re

from app.models import Consciousness, HeardVitals

# ─── spoken numbers → digits ("ninety four" → 94, "one twenty" → 120, "thirty seven point two" → 37.2) ────────────
UNITS = {w: i for i, w in enumerate(["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"])}
TEENS = {w: i + 10 for i, w in enumerate(["ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"])}
TENS = {w: (i + 2) * 10 for i, w in enumerate(["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"])}
_WORD = "|".join([*UNITS, *TEENS, *TENS, "hundred", "point", "oh"])
NUMBER_RUN = re.compile(rf"\b(?:{_WORD})(?:(?:[\s-]+|\s+and\s+)(?:{_WORD}))*\b")


def _two_digit(ws: list[str]) -> int | None:
    if not ws:
        return 0
    if len(ws) == 1:
        w = ws[0]
        return UNITS.get(w, TEENS.get(w, TENS.get(w)))
    if len(ws) == 2 and ws[0] in TENS and UNITS.get(ws[1], 0) > 0:
        return TENS[ws[0]] + UNITS[ws[1]]
    if len(ws) == 2 and ws[0] == "oh" and ws[1] in UNITS:  # "one oh five"
        return UNITS[ws[1]]
    return None


def _integer(ws: list[str]) -> int | None:
    if "hundred" in ws:
        k = ws.index("hundred")
        lead, rest = _two_digit(ws[:k] or ["one"]), _two_digit(ws[k + 1:])
        return None if lead is None or rest is None or lead > 9 else lead * 100 + rest
    if (n := _two_digit(ws)) is not None:
        return n
    # "one twenty" is how a blood pressure is said
    if len(ws) > 1 and UNITS.get(ws[0], 0) > 0 and (rest := _two_digit(ws[1:])) is not None:
        return UNITS[ws[0]] * 100 + rest
    return None


def _number(run: str) -> str | None:
    ws = [w for w in re.split(r"[\s-]+", run) if w != "and"]
    whole, _, frac = " ".join(ws).partition("point")
    n = _integer(whole.split())
    if n is None:
        return None
    if not frac.strip():
        return str(n)
    digits = [UNITS.get(w) for w in frac.split()]
    return None if None in digits else f"{n}.{''.join(map(str, digits))}"


def digits(text: str) -> str:
    """Lowercased, with spoken numbers written as digits. Runs that don't read as one number are left alone."""
    return NUMBER_RUN.sub(lambda m: _number(m.group(0)) or m.group(0), text.lower())


# ─── the vitals ──────────────────────────────────────────────────────────────────────────────────────────────────
NUM = r"(\d{1,3}(?:\.\d)?)"
# what people put between a name and its value: "sats are 94", "BP of 120", "temp is now 37"
GAP = r"[\s:=,-]*(?:(?:is|are|was|of|at|now|about|around|reading|still)[\s:,]+)*"

SPO2 = [
    re.compile(rf"\b(?:sp\s?o\s?2|sp\s?02|o2 sats?|oxygen sat(?:uration)?s?|sat(?:uration)?s?|saturating|pulse ox(?:imetry)?){GAP}{NUM}"),
    re.compile(rf"\b{NUM}\s*(?:%|percent|per cent)\s*(?:sats|saturation|sp\s?o\s?2|on (?:room )?air|on (?:o2|oxygen))\b"),
]
BP = [
    re.compile(rf"\b(?:bp|b\.p\.|blood pressure|pressure|systolic){GAP}(\d{{2,3}})(?:\s*(?:/|over)\s*(\d{{2,3}}))?"),
    re.compile(r"\b(\d{2,3})\s*(?:/|over)\s*(\d{2,3})\b"),
]
TEMP = [
    re.compile(rf"\b(?:temp(?:erature)?|tympanic|febrile at){GAP}{NUM}\s*(?:°|degrees?)?\s*(c|celsius|centigrade|f|fahrenheit)?\b"),
    re.compile(rf"\b{NUM}\s*(?:°|degrees?)\s*(c|celsius|centigrade|f|fahrenheit)?\b"),
]
HR = [
    re.compile(rf"\b(?:heart rate|hr|pulse(?! ox)(?: rate)?){GAP}{NUM}"),
    re.compile(rf"\b{NUM}\s*(?:bpm|beats (?:per|a) minute)\b"),
]
RR = [
    re.compile(rf"\b(?:resp(?:iratory|iration)?s?(?: rate)?|rr|breathing(?: rate)?){GAP}{NUM}"),
    re.compile(rf"\b{NUM}\s*breaths\b"),
]
ON_AIR = re.compile(r"\bon (?:room )?air\b")
ON_OXYGEN = re.compile(r"\bon (?:\d+\s*(?:l|litres?|liters?)(?: of)?\s*)?(?:oxygen|o2)\b|\bnon-?rebreather\b|\bnasal cannula\b")

ACVPU = [
    (Consciousness.unresponsive, re.compile(r"\b(?:unresponsive|unconscious|no response|not responding|gcs (?:of )?3)\b")),
    (Consciousness.pain, re.compile(r"\b(?:respond(?:s|ing)? (?:only )?to pain(?:ful stimuli)?|pain[- ]responsive|p on a?c?vpu)\b")),
    (Consciousness.voice, re.compile(r"\b(?:respond(?:s|ing)? (?:only )?to (?:voice|verbal)|voice[- ]responsive|v on a?c?vpu)\b")),
    (Consciousness.confused, re.compile(r"\b(?:(?:new(?:ly)? )?confus(?:ed|ion)|c on a?c?vpu)\b")),
    (Consciousness.alert, re.compile(r"\b(?:alert(?! (?:the|to|team|hospital|them|receiving))|gcs (?:of )?15|a on a?c?vpu)\b")),
]
LETTER = re.compile(r"\ba?c?vpu (?:is |of )?([acvpu])\b")
NEGATED = re.compile(r"\b(?:not|no|isn't|wasn't|doesn't|never)\s+(?:\w+\s+)?$")


def _first(patterns: list[re.Pattern], text: str, lo: float, hi: float) -> tuple[float, re.Match] | None:
    for p in patterns:
        for m in p.finditer(text):
            v = float(m.group(1))
            if lo <= v <= hi:
                return v, m
    return None


def _temperature(text: str) -> float | None:
    for named, p in zip((True, False), TEMP, strict=True):
        for m in p.finditer(text):
            raw, unit = m.group(1), (m.group(2) or "")
            v = float(raw)
            # "sat up at 30 degrees" is an angle: without a name, a temperature needs a unit, a decimal or a body's range
            if not named and not unit and "." not in raw and not (35 <= v <= 42 or 95 <= v <= 108):
                continue
            if unit.startswith("f") or (not unit and 90 <= v <= 110):
                v = round((v - 32) * 5 / 9, 1)
            if 30 <= v <= 44:
                return v
    return None


def _consciousness(text: str) -> Consciousness | None:
    """The last state said wins: "confused earlier, now alert" is alert."""
    found: list[tuple[int, Consciousness]] = [(m.start(), Consciousness(m.group(1).upper())) for m in LETTER.finditer(text)]
    for level, p in ACVPU:
        for m in p.finditer(text):
            # "not responding" is itself the finding; anything else said with a "not" in front is not
            if level != Consciousness.unresponsive and NEGATED.search(text[max(0, m.start() - 20): m.start()]):
                continue
            found.append((m.start(), level))
    return max(found, key=lambda f: f[0])[1] if found else None


def parse(text: str) -> HeardVitals:
    t = digits(text)
    heard = HeardVitals(transcript=text.strip())
    if spo2 := _first(SPO2, t, 50, 100):
        heard.spo2 = spo2[0]
        # air or oxygen only means something next to a saturation
        if ON_OXYGEN.search(t):
            heard.on_oxygen = True
        elif ON_AIR.search(t):
            heard.on_oxygen = False
    for p in BP:
        m = next((m for m in p.finditer(t) if 50 <= int(m.group(1)) <= 260
                  and (m.group(2) is None or 20 <= int(m.group(2)) < int(m.group(1)))), None)
        if m:
            heard.systolic_bp = float(m.group(1))
            heard.diastolic_bp = float(m.group(2)) if m.group(2) else None
            break
    heard.temperature_c = _temperature(t)
    if hr := _first(HR, t, 20, 250):
        heard.heart_rate = hr[0]
    if rr := _first(RR, t, 4, 60):
        heard.resp_rate = rr[0]
    heard.consciousness = _consciousness(t)
    return heard


def found(h: HeardVitals) -> bool:
    return any(v is not None for v in (h.spo2, h.systolic_bp, h.temperature_c, h.heart_rate, h.resp_rate, h.consciousness))


def labels(h: HeardVitals) -> list[str]:
    """Chips for what was heard: 'SpO₂ 94% on air', 'BP 120/80', 'Temp 37.2 °C', 'Alert'."""
    out: list[str] = []
    if h.spo2 is not None:
        air = "" if h.on_oxygen is None else " on oxygen" if h.on_oxygen else " on air"
        out.append(f"SpO₂ {h.spo2:g}%{air}")
    if h.systolic_bp is not None:
        out.append(f"BP {h.systolic_bp:g}" + (f"/{h.diastolic_bp:g}" if h.diastolic_bp is not None else ""))
    if h.temperature_c is not None:
        out.append(f"Temp {h.temperature_c:g} °C")
    if h.heart_rate is not None:
        out.append(f"Pulse {h.heart_rate:g}")
    if h.resp_rate is not None:
        out.append(f"Breathing {h.resp_rate:g}/min")
    if h.consciousness is not None:
        out.append({"A": "Alert", "C": "Confused", "V": "Responds to voice", "P": "Responds to pain",
                    "U": "Unresponsive"}[h.consciousness.value])
    return out
