# Latest-value tracking, Presage validity flags and the simulated vitals source.
from __future__ import annotations

import math
import random
from datetime import datetime

from app.models import LatestValue, SimProfile, VitalsReading, VitalsSource

FIELDS = ["heart_rate", "resp_rate", "hrv_rmssd", "spo2", "on_oxygen", "systolic_bp", "temperature_c", "consciousness"]

# Presage SmartSpectra model card: pulse validated 40–110 BPM, breathing 5–40 /min (DEMO: shown as a flag, not hidden).
PRESAGE_RANGES = {"heart_rate": (40, 110), "resp_rate": (5, 40)}
LOW_CONFIDENCE = 0.6


def presage_flag(field: str, value: float, source: VitalsSource) -> str | None:
    if source != VitalsSource.presage or field not in PRESAGE_RANGES:
        return None
    lo, hi = PRESAGE_RANGES[field]
    if value < lo or value > hi:
        return f"Outside Presage validated range ({lo}–{hi}) — confirm manually"
    return None


def update_latest(latest: dict[str, LatestValue], reading: VitalsReading) -> dict[str, LatestValue]:
    """Merge a reading into the per-field latest values (low-quality readings never overwrite)."""
    if reading.low_quality:
        return latest
    out = dict(latest)
    for field in FIELDS:
        value = getattr(reading, field)
        if value is None:
            continue
        prev = out.get(field)
        if prev is not None and prev.at > reading.recorded_at:
            continue
        v = value.value if hasattr(value, "value") else value
        flag = presage_flag(field, float(v), reading.source) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
        out[field] = LatestValue(value=v, at=reading.recorded_at, source=reading.source, flag=flag)
    return out


def simulated_values(profile: SimProfile, started: datetime, at: datetime, seed: int) -> dict[str, float]:
    """Plausible contactless HR / RR / HRV with a gentle drift and breathing-coupled noise (clearly labelled)."""
    hours = max(0.0, (at - started).total_seconds() / 3600)
    rng = random.Random(seed + int(at.timestamp()))
    wobble = math.sin(at.timestamp() / 47.0)
    hr = profile.heart_rate + profile.heart_rate_per_hour * hours + 2.2 * wobble + rng.uniform(-1.5, 1.5)
    rr = profile.resp_rate + profile.resp_rate_per_hour * hours + rng.uniform(-0.8, 0.8)
    hrv = max(5.0, profile.hrv_rmssd - 4 * hours + rng.uniform(-2, 2))
    return {"heart_rate": round(hr), "resp_rate": round(rr), "hrv_rmssd": round(hrv, 1)}
