# F-M2.3 NEWS2 (Royal College of Physicians, SpO2 Scale 1). Pure, deterministic, unit-tested.
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.models import News2Result, VitalsReading

PARAMS = ["resp_rate", "spo2", "on_oxygen", "systolic_bp", "heart_rate", "consciousness", "temperature_c"]
LABELS = {
    "resp_rate": "RR",
    "spo2": "SpO₂",
    "on_oxygen": "Air/O₂",
    "systolic_bp": "SBP",
    "heart_rate": "HR",
    "consciousness": "ACVPU",
    "temperature_c": "Temp",
}
LOOKBACK_MIN = 30


def score_resp_rate(v: float) -> int:
    if v <= 8:
        return 3
    if v <= 11:
        return 1
    if v <= 20:
        return 0
    if v <= 24:
        return 2
    return 3


def score_spo2(v: float) -> int:
    if v <= 91:
        return 3
    if v <= 93:
        return 2
    if v <= 95:
        return 1
    return 0


def score_on_oxygen(v: bool) -> int:
    return 2 if v else 0


def score_systolic_bp(v: float) -> int:
    if v <= 90:
        return 3
    if v <= 100:
        return 2
    if v <= 110:
        return 1
    if v <= 219:
        return 0
    return 3


def score_heart_rate(v: float) -> int:
    if v <= 40:
        return 3
    if v <= 50:
        return 1
    if v <= 90:
        return 0
    if v <= 110:
        return 1
    if v <= 130:
        return 2
    return 3


def score_consciousness(v: str) -> int:
    value = v.value if hasattr(v, "value") else v
    return 0 if value == "A" else 3


def score_temperature(v: float) -> int:
    v = round(v, 1)
    if v <= 35.0:
        return 3
    if v <= 36.0:
        return 1
    if v <= 38.0:
        return 0
    if v <= 39.0:
        return 1
    return 2


SCORERS = {
    "resp_rate": score_resp_rate,
    "spo2": score_spo2,
    "on_oxygen": score_on_oxygen,
    "systolic_bp": score_systolic_bp,
    "heart_rate": score_heart_rate,
    "consciousness": score_consciousness,
    "temperature_c": score_temperature,
}


def band_for(total: int, any_single_3: bool) -> str:
    if total >= 7:
        return "high"
    if total >= 5:
        return "medium"
    if any_single_3:
        return "low_medium"
    return "low"


def score_values(values: dict[str, Any]) -> News2Result:
    components: dict[str, int | None] = {}
    missing: list[str] = []
    for param in PARAMS:
        value = values.get(param)
        if value is None:
            components[param] = None
            missing.append(param)
            continue
        components[param] = SCORERS[param](value)
    scored = [c for c in components.values() if c is not None]
    if not scored:
        return News2Result(
            total=None, components=components, any_single_3=False, band=None, complete=False, missing=missing
        )
    total = sum(scored)
    any3 = any(c == 3 for c in scored)
    clean = {k: (v.value if hasattr(v, "value") else v) for k, v in values.items() if v is not None}
    return News2Result(
        total=total,
        components=components,
        any_single_3=any3,
        band=band_for(total, any3),  # type: ignore[arg-type]
        complete=not missing,
        missing=missing,
        values_used=clean,
    )


def latest_values(readings: list[VitalsReading], now: datetime, lookback_min: int = LOOKBACK_MIN) -> dict[str, Any]:
    """Latest non-null value per parameter within the lookback window; low-quality readings excluded (F-M6.4)."""
    cutoff = now - timedelta(minutes=lookback_min)
    values: dict[str, Any] = {}
    for r in sorted(readings, key=lambda r: r.recorded_at, reverse=True):
        if r.recorded_at < cutoff or r.recorded_at > now + timedelta(minutes=1) or r.low_quality:
            continue
        for param in PARAMS:
            if param in values:
                continue
            value = getattr(r, param)
            if value is not None:
                values[param] = value
    return values


def compute(readings: list[VitalsReading], now: datetime) -> News2Result | None:
    if not readings:
        return None
    return score_values(latest_values(readings, now))


def partial_label(result: News2Result) -> str:
    present = [LABELS[p] for p in PARAMS if result.components.get(p) is not None]
    return f"Partial NEWS2 ({', '.join(present)} only)"
