# Deterioration alerts (deterministic). Raised once, spoken in the vehicle and shown at the hospital.
from __future__ import annotations

from datetime import datetime, timedelta

from app.core.scan_trend import ScanTrend
from app.models import Alert, AlertLevel, DeteriorationForecast, LatestValue, News2Result, VitalsSource


def evaluate(
    news2: News2Result | None,
    latest: dict[str, LatestValue],
    forecast: DeteriorationForecast | None,
    previous: list[Alert],
    now: datetime,
    scan_trend: ScanTrend | None = None,
) -> list[Alert]:
    """Current active alerts. Keeps the original `since` for alerts that persist."""
    found: list[tuple[str, AlertLevel, str]] = []
    if news2 and news2.total is not None:
        if news2.total >= 7:
            found.append(("news2_high", AlertLevel.critical, f"NEWS2 {news2.total} — high risk"))
        elif news2.total >= 5 or news2.any_single_3:
            found.append(("news2_medium", AlertLevel.warning, f"NEWS2 {news2.total} — urgent review"))

    def num(field: str) -> float | None:
        lv = latest.get(field)
        return float(lv.value) if lv is not None and isinstance(lv.value, (int, float)) and not isinstance(lv.value, bool) else None

    spo2 = num("spo2")
    if spo2 is not None and spo2 <= 91:
        found.append(("spo2_low", AlertLevel.critical, f"SpO₂ {spo2:g}%"))
    # Presage's clearance is for spot checks on calm, healthy adults: an extreme value from the camera alone is a
    # prompt to measure by hand, never a critical alert on its own. Crew-entered values alert as before.
    def camera(field: str) -> bool:
        lv = latest.get(field)
        return lv is not None and lv.source == VitalsSource.presage

    hr = num("heart_rate")
    if hr is not None and (hr >= 131 or hr <= 40):
        found.append(("hr_extreme", AlertLevel.warning, f"Camera estimate: heart rate {hr:g} — confirm with a monitor")
                     if camera("heart_rate") else ("hr_extreme", AlertLevel.critical, f"Heart rate {hr:g}"))
    rr = num("resp_rate")
    if rr is not None and (rr >= 25 or rr <= 8):
        found.append(("rr_extreme", AlertLevel.warning, f"Camera estimate: breathing rate {rr:g} — count it by hand")
                     if camera("resp_rate") else ("rr_extreme", AlertLevel.critical, f"Breathing rate {rr:g}"))
    # two stable Presage spot checks minutes apart that moved a lot: measure properly now
    if scan_trend and scan_trend.worrying:
        found.append(("presage_trend", AlertLevel.warning, scan_trend.text))
    if forecast and forecast.hr_slope_per_hour is not None and forecast.hr_slope_per_hour >= 15:
        found.append(("hr_rising", AlertLevel.warning, f"Heart rate rising (+{forecast.hr_slope_per_hour:g}/h)"))
    worsening = forecast and forecast.trend == "worsening" and (forecast.minutes_to_news2_7 or 0) > 0
    if worsening and (not news2 or (news2.total or 0) < 7):
        found.append((
            "news2_rising",
            AlertLevel.warning,
            f"Trend suggests NEWS2 may reach 7 in ~{int(forecast.minutes_to_news2_7)} min",
        ))

    since = {a.code: a.since for a in previous}
    current = [Alert(code=c, level=lvl, text=t, since=since.get(c, now)) for c, lvl, t in found]
    # hysteresis: an alert stays active for HOLD after it was raised, so a value wobbling across a NEWS2 boundary
    # doesn't flap the banner (a more severe alert of the same family replaces it)
    codes = {a.code for a in current}
    for a in previous:
        family = a.code.split("_")[0]
        if a.code in codes or any(c.split("_")[0] == family for c in codes):
            continue
        if now - a.since < HOLD:
            current.append(a)
    return current


HOLD = timedelta(minutes=10)
REANNOUNCE = timedelta(minutes=15)


def new_alerts(before: list[Alert], after: list[Alert], announced: dict[str, datetime] | None = None,
               now: datetime | None = None) -> list[Alert]:
    """Alerts to announce: newly active and not announced in the last REANNOUNCE window."""
    codes = {a.code for a in before}
    fresh = [a for a in after if a.code not in codes]
    if announced is None or now is None:
        return fresh
    return [a for a in fresh if a.code not in announced or now - announced[a.code] >= REANNOUNCE]
