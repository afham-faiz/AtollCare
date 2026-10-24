# Helpers to build pure (DB-free) cases from scenario files for engine tests.
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from uuid import uuid4

from app.core import decision, fallback_intake, refdata, seed
from app.core.clock import tz
from app.core.forecast import bucket_news2
from app.models import Case, CaseHeadline, CaseMeta, GeoPoint, Patient, TrendBucket, VitalsReading, Weather


def at_local(hhmm: str, day: date = date(2026, 10, 24)) -> datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, time(hh, mm), tzinfo=tz()).astimezone(UTC)


def case_from_scenario(scenario_id: str, now: datetime | None = None) -> tuple[Case, datetime]:
    sc = refdata.scenarios()[scenario_id]
    now = now or at_local(sc["clock"])
    first = min(s["at_min"] for s in sc["steps"])
    created = now + timedelta(minutes=min(first, 0))
    origin = refdata.facility(sc["origin_facility_id"])
    assert origin
    cid = uuid4()
    vitals: list[VitalsReading] = []
    intake = None
    for step in sc["steps"]:
        at = now + timedelta(minutes=step["at_min"])
        if at > now:
            continue
        if step["action"] == "intake":
            intake = fallback_intake.extract(sc["intake_text"], at)
        if step["action"] == "vitals":
            vitals.append(VitalsReading(id=uuid4(), case_id=cid, recorded_at=at, **step["vitals"]))
    case = Case(
        id=cid,
        short_code="AC-TEST",
        created_at=created,
        updated_at=now,
        status="submitted",
        origin_facility_id=origin.id,
        origin_point=GeoPoint(lat=origin.lat, lng=origin.lng),
        patient=Patient(**sc.get("patient", {})),
        intake=intake,
        vitals=vitals,
        headline=CaseHeadline(elapsed_min=0, projected_total_min=None, saved_vs_baseline_min=None, text=""),
        meta=CaseMeta(submitted_at=now),
    )
    return case, now


def trend_from_vitals(vitals: list[VitalsReading]) -> list[TrendBucket]:
    buckets = [
        TrendBucket(
            t=v.recorded_at.replace(second=0, microsecond=0),
            hr=v.heart_rate, rr=v.resp_rate, spo2=v.spo2, sbp=v.systolic_bp, temp=v.temperature_c,
        )
        for v in vitals
    ]
    return bucket_news2(buckets)


def ctx_for(now: datetime, weather: Weather | None = None, **kw) -> decision.AssessContext:
    return decision.AssessContext(
        now=now,
        weather=weather or Weather(),
        assets=seed.seed_assets(),
        capacity={c.facility_id: c for c in seed.seed_capacity(now)},
        **kw,
    )
