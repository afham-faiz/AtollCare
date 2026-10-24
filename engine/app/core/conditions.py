# F-M2.4 Conditions, time windows, required capabilities, severity, candidate destinations.
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.core import refdata
from app.models import SEVERITY_ORDER, Facility, HospitalCapacity, Intake, News2Result, Severity


@dataclass
class ConditionContext:
    condition_id: str
    probability: float
    spec: dict[str, Any]
    window_min: float | None
    window_start: datetime
    time_since_start_min: float
    onset_confidence: str

    @property
    def interim(self) -> dict[str, Any] | None:
        return self.spec.get("interim")


def select_primary(intake: Intake | None) -> tuple[str, float]:
    """primary = argmax(probability × 1.5 if time-critical window ≤ 120 min)."""
    if intake is None or not intake.suspected_conditions:
        return "other", 0.0
    cfg = refdata.conditions_config()
    weight = cfg.get("time_critical_weight", 1.5)
    max_window = cfg.get("time_critical_weight_max_window", 120)
    known = refdata.conditions()
    best_id, best_prob, best_score = "other", 0.0, -1.0
    for sc in intake.suspected_conditions:
        spec = known.get(sc.condition_id)
        if spec is None:
            continue
        window = spec.get("window_min")
        factor = weight if window is not None and window <= max_window else 1.0
        score = sc.probability * factor
        if score > best_score:
            best_id, best_prob, best_score = sc.condition_id, sc.probability, score
    return best_id, best_prob


def condition_context(intake: Intake | None, created_at: datetime, now: datetime) -> ConditionContext:
    cid, prob = select_primary(intake)
    spec = refdata.conditions()[cid]
    onset_confidence = intake.onset_confidence if intake else "unknown"
    start = created_at
    if spec.get("window_from") == "onset" and intake and intake.onset_time is not None:
        start = intake.onset_time
    if spec.get("window_from") == "first_medical_contact":
        onset_confidence = "exact"
    elapsed = max(0.0, (now - start).total_seconds() / 60)
    return ConditionContext(
        condition_id=cid,
        probability=prob,
        spec=spec,
        window_min=spec.get("window_min"),
        window_start=start,
        time_since_start_min=elapsed,
        onset_confidence=onset_confidence,
    )


def severity_for(news2: News2Result | None, intake: Intake | None, ctx: ConditionContext) -> Severity:
    """NEWS2 band → severity; red flags + time-critical condition (p ≥ 0.4) → critical. Partial NEWS2 never
    downgrades severity implied by red flags."""
    base = news2.band if news2 and news2.band else "low"
    level = SEVERITY_ORDER.index(base)
    red_flags = bool(intake and intake.red_flags)
    threshold = refdata.conditions_config().get("critical_red_flag_probability", 0.4)
    if red_flags and ctx.spec.get("time_critical") and ctx.probability >= threshold:
        return Severity.critical
    if red_flags:
        level = max(level, SEVERITY_ORDER.index("high"))
    return Severity(SEVERITY_ORDER[level])


def required_capabilities(ctx: ConditionContext, severity: Severity) -> list[str]:
    caps = list(ctx.spec.get("required_capabilities", []))
    if SEVERITY_ORDER.index(severity.value) >= SEVERITY_ORDER.index("high"):
        caps += [c for c in ctx.spec.get("high_severity_capabilities", []) if c not in caps]
    return caps


def capacity_allows(fac: Facility, caps: list[str], capacity: dict[str, HospitalCapacity]) -> tuple[bool, str]:
    cap = capacity.get(fac.id)
    if cap is None:
        return True, ""
    if "cath_lab" in caps and cap.cath_lab_available is False:
        return False, f"{fac.name}: cath lab unavailable"
    if "icu" in caps and cap.icu_beds_free is not None and cap.icu_beds_free <= 0:
        return False, f"{fac.name}: no ICU beds"
    if "ct" in caps and cap.ct_available is False:
        return False, f"{fac.name}: CT unavailable"
    if "blood_bank" in caps and cap.blood_bank_units is not None and cap.blood_bank_units <= 0:
        return False, f"{fac.name}: blood bank empty"
    return True, ""


def candidate_destinations(
    caps: list[str],
    capacity: dict[str, HospitalCapacity],
    exclude: set[str] | None = None,
) -> tuple[list[Facility], list[str]]:
    """Facilities whose capabilities ⊇ required and whose live capacity allows it. Returns (candidates, reasons)."""
    exclude = exclude or set()
    out: list[Facility] = []
    rejected: list[str] = []
    for fac in refdata.facilities().values():
        if fac.type == "airport" or not set(caps) <= set(fac.capabilities):
            continue
        if fac.id in exclude:
            rejected.append(f"{fac.name}: declined referral")
            continue
        ok, reason = capacity_allows(fac, caps, capacity)
        if not ok:
            rejected.append(reason)
            continue
        out.append(fac)
    return out, rejected


def interim_facilities(
    interim: dict[str, Any], origin: Facility, capacity: dict[str, HospitalCapacity], exclude: set[str]
) -> list[Facility]:
    caps = interim.get("capabilities", [])
    out: list[Facility] = []
    for fac in refdata.facilities().values():
        if fac.type == "airport" or fac.id in exclude or not set(caps) <= set(fac.capabilities):
            continue
        if fac.id == origin.id and not interim.get("allow_origin"):
            continue
        if fac.type == "health_centre" and fac.id != origin.id:
            continue
        if not capacity_allows(fac, caps, capacity)[0]:
            continue
        out.append(fac)
    return out
