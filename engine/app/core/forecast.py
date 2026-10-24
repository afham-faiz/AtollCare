# Deterioration forecast — OLS on (minutes, NEWS2) over the last ≤ 60 min of 1-min buckets (Tiger Data continuous
# aggregate, raw fallback). Copy shown to users is always hedged ("Trend suggests…").
from __future__ import annotations

from datetime import datetime, timedelta

from app.core import news2 as news2_mod
from app.models import DeteriorationForecast, TrendBucket

BUCKET_FIELDS = {"hr": "heart_rate", "rr": "resp_rate", "spo2": "spo2", "sbp": "systolic_bp", "temp": "temperature_c"}


def bucket_news2(buckets: list[TrendBucket], extra: dict[str, object] | None = None) -> list[TrendBucket]:
    """Fill TrendBucket.news2 using carry-forward of the last known value per parameter. Parameters first measured
    later are back-filled with their first value, so a partial → complete jump is not mistaken for deterioration.
    `extra` supplies non-aggregated parameters (consciousness, on_oxygen) from the latest raw reading."""
    ordered = sorted(buckets, key=lambda x: x.t)
    carried: dict[str, object] = dict(extra or {})
    for short, param in BUCKET_FIELDS.items():
        first = next((getattr(b, short) for b in ordered if getattr(b, short) is not None), None)
        if first is not None:
            carried[param] = first
    out: list[TrendBucket] = []
    for b in ordered:
        for short, param in BUCKET_FIELDS.items():
            value = getattr(b, short)
            if value is not None:
                carried[param] = value
        result = news2_mod.score_values(carried)
        out.append(b.model_copy(update={"news2": result.total}))
    return out


def _ols(xs: list[float], ys: list[float]) -> tuple[float, float, float | None]:
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return 0.0, my, None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx
    intercept = my - slope * mx
    ss_tot = sum((y - my) ** 2 for y in ys)
    ss_res = sum((y - (intercept + slope * x)) ** 2 for x, y in zip(xs, ys))
    r2 = None if ss_tot == 0 else max(0.0, 1 - ss_res / ss_tot)
    return slope, intercept, r2


def forecast(
    buckets: list[TrendBucket], now: datetime, arrive_at: datetime | None, window_min: int = 60
) -> DeteriorationForecast | None:
    cutoff = now - timedelta(minutes=window_min)
    pts = [b for b in buckets if b.news2 is not None and cutoff <= b.t <= now + timedelta(minutes=1)]
    if len(pts) < 3:
        return None
    xs = [(b.t - now).total_seconds() / 60 for b in pts]
    ys = [float(b.news2) for b in pts]  # type: ignore[arg-type]
    slope, intercept, r2 = _ols(xs, ys)
    slope_h = slope * 60

    def param_slope(short: str) -> float | None:
        pp = [(x, getattr(b, short)) for x, b in zip(xs, pts) if getattr(b, short) is not None]
        if len(pp) < 3:
            return None
        s, _, _ = _ols([p[0] for p in pp], [float(p[1]) for p in pp])
        return round(s * 60, 1)

    current = intercept  # fitted value at x = 0 (now)
    span = max(xs) - min(xs)
    projected = None
    horizon = None
    if arrive_at is not None:
        # never extrapolate further ahead than 2× the observed span
        mins = min(max(0.0, (arrive_at - now).total_seconds() / 60), 2 * span)
        projected = round(min(20.0, max(0.0, current + slope * mins)), 1)
        horizon = round(mins, 1)
    minutes_to_7 = None
    if slope > 0 and current < 7:
        minutes_to_7 = round((7 - current) / slope, 0)
    elif current >= 7:
        minutes_to_7 = 0.0
    trend = "stable"
    if slope_h >= 1:
        trend = "worsening"
    elif slope_h <= -1:
        trend = "improving"
    confidence = "medium" if len(pts) >= 6 and r2 is not None and r2 >= 0.5 else "low"
    return DeteriorationForecast(
        slope_per_hour=round(slope_h, 2),
        projected_news2_at_arrival=projected,
        minutes_to_news2_7=minutes_to_7,
        trend=trend,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        points_used=len(pts),
        horizon_min=horizon,
        r2=None if r2 is None else round(r2, 2),
        hr_slope_per_hour=param_slope("hr"),
        rr_slope_per_hour=param_slope("rr"),
    )
