# Network insights: synthetic history for the demo (clearly flagged `seeded`) and the in-memory aggregation that
# mirrors the TimescaleDB queries in db.PgRepo.insights. DEMO ASSUMPTION — every seeded number is illustrative.
from __future__ import annotations

import math
import random
import statistics
import uuid
import zlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from app.core import regions
from app.models import (
    InsightsChannel,
    InsightsDay,
    InsightsGroup,
    InsightsResponse,
    InsightsTotals,
    Region,
    Transfer,
    TransferLogRow,
    TransportMode,
)

CONDITIONS = [
    ("Acute coronary syndrome", 0.24), ("Stroke", 0.12), ("Major trauma", 0.16), ("Obstetric emergency", 0.12),
    ("Sepsis", 0.14), ("Respiratory distress", 0.12), ("Acute abdomen", 0.10),
]
MODE_WEIGHT = {TransportMode.boat: 0.68, TransportMode.road: 0.68, TransportMode.helicopter: 0.12, TransportMode.plane: 0.2}
DISPATCH_MIN = {TransportMode.road: 8, TransportMode.boat: 20, TransportMode.helicopter: 30, TransportMode.plane: 45}
HOUR_WEIGHTS = [2, 1, 1, 1, 1, 2, 4, 6, 7, 8, 8, 8, 7, 7, 7, 7, 8, 8, 7, 6, 5, 4, 3, 3]  # local departure hour


def median(xs: list[float]) -> float | None:
    return round(statistics.median(xs), 1) if xs else None


def pctl(xs: list[float], q: float) -> float | None:
    """Linear interpolation, same as Postgres percentile_cont."""
    if not xs:
        return None
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return round(s[lo] + (s[hi] - s[lo]) * (pos - lo), 1)


def mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 1) if xs else None


def _pick(rng: random.Random, weighted: list[tuple[object, float]]) -> object:
    return rng.choices([w[0] for w in weighted], weights=[w[1] for w in weighted])[0]


def seed_rows(region: Region, days: int, now: datetime, rng_seed: int | None = None) -> list[TransferLogRow]:
    """`days` of completed transfers. The first ~45% of the window is the phone/radio baseline (the hospital hears a
    short pre-alert near arrival); after that AtollCare handoffs are sent shortly after departure. Deterministic for a
    given region, window and day so a re-seed reproduces the same chart."""
    key = f"{region.id}:{days}:{now.date().isoformat()}".encode()
    rng = random.Random(rng_seed if rng_seed is not None else zlib.crc32(key))
    tz = ZoneInfo(region.timezone)
    hospitals = [f for f in region.facilities if f.kind == "hospital"]
    clinics = [f for f in region.facilities if f.kind == "clinic"] or hospitals
    modes = [m for m in region.modes if m in MODE_WEIGHT]
    info = regions.modes()
    start = now - timedelta(days=days)
    rollout = now - timedelta(days=days * 0.55)
    rows: list[TransferLogRow] = []

    for d in range(days, 0, -1):
        day = (now - timedelta(days=d)).astimezone(tz).replace(hour=0, minute=0, second=0, microsecond=0)
        weekend = day.weekday() >= 5
        count = max(2, round(rng.gauss(9 if not weekend else 7, 2.2)))
        for _ in range(count):
            hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
            departed = day + timedelta(hours=hour, minutes=rng.randint(0, 59))
            if departed >= now or departed < start:
                continue
            origin = rng.choice(clinics)
            # the main referral hospital takes most transfers
            dest = hospitals[0] if rng.random() < 0.6 else rng.choice(hospitals)
            if dest.id == origin.id:
                dest = hospitals[0]
            mode = _pick(rng, [(m, MODE_WEIGHT[m]) for m in modes])
            mi = info[mode]  # type: ignore[index]
            dist = regions.haversine_km(regions.point(origin), regions.point(dest))
            journey = max(12.0, dist * mi.detour / mi.speed_kmh * 60 + DISPATCH_MIN[mode] * rng.uniform(0.4, 1.2)  # type: ignore[index]
                          + rng.gauss(0, 6))
            arrived = departed + timedelta(minutes=journey)
            if arrived > now:
                continue
            atollcare = departed >= rollout
            if atollcare:
                handoff = departed + timedelta(minutes=rng.uniform(3, 14))
                accept = max(0.8, rng.lognormvariate(math.log(4.5), 0.55))
                prepared = rng.random() < 0.86
            else:
                # radio / phone pre-alert: often late, sometimes missing entirely
                if rng.random() < 0.22:
                    handoff, accept, prepared = None, None, False
                else:
                    handoff = arrived - timedelta(minutes=min(journey * 0.9, max(3.0, rng.gauss(14, 7))))
                    accept = max(2.0, rng.lognormvariate(math.log(11), 0.6))
                    prepared = rng.random() < 0.35
            accepted = handoff + timedelta(minutes=accept) if handoff and accept else None
            if accepted and accepted > arrived:
                accepted = arrived
                accept = (arrived - handoff).total_seconds() / 60 if handoff else None
            warning = (arrived - handoff).total_seconds() / 60 if handoff else None
            rows.append(TransferLogRow(
                transfer_id=uuid.UUID(int=rng.getrandbits(128), version=4),
                departed_at=departed, region_id=region.id, origin_id=origin.id, destination_id=dest.id,
                mode=mode, channel="atollcare" if atollcare else "radio",  # type: ignore[arg-type]
                condition=str(_pick(rng, CONDITIONS)), handoff_at=handoff, accepted_at=accepted, arrived_at=arrived,
                journey_min=round(journey, 1), warning_min=round(warning, 1) if warning is not None else None,
                accept_min=round(accept, 1) if accept is not None else None, prepared=prepared,
                peak_news2=max(0, min(15, round(rng.gauss(5, 2.5)))), seeded=True,
            ))
    return rows


def row_from_transfer(t: Transfer) -> TransferLogRow:
    """A live transfer becomes a log row when it arrives."""
    arrived = t.arrived_at or t.updated_at

    def minutes(a: datetime | None, b: datetime | None) -> float | None:
        return round((b - a).total_seconds() / 60, 1) if a and b else None

    return TransferLogRow(
        transfer_id=t.id, departed_at=t.departed_at, region_id=t.region_id, origin_id=t.origin_id,
        destination_id=t.destination_id, mode=t.mode, channel="atollcare",
        condition=t.briefing.suspected_condition if t.briefing else None,
        handoff_at=t.handoff_at, accepted_at=t.acceptance.at if t.acceptance else None, arrived_at=arrived,
        journey_min=minutes(t.departed_at, arrived) or 0.0, warning_min=minutes(t.handoff_at, arrived),
        accept_min=minutes(t.handoff_at, t.acceptance.at if t.acceptance else None),
        prepared=bool(t.acceptance and t.acceptance.prepare), peak_news2=t.news2.total if t.news2 else None,
    )


def aggregate(rows: list[TransferLogRow], region_id: str, days: int, since: datetime, tz: str,
              source: str = "memory", query_ms: float = 0.0) -> InsightsResponse:
    """In-memory equivalent of PgRepo.insights (used by MemoryRepo and the tests)."""
    rows = [r for r in rows if r.region_id == region_id and r.departed_at >= since]
    zone = ZoneInfo(tz)

    def vals(rs: list[TransferLogRow], attr: str) -> list[float]:
        return [getattr(r, attr) for r in rs if getattr(r, attr) is not None]

    def pct_prepared(rs: list[TransferLogRow]) -> float | None:
        return round(100 * sum(r.prepared for r in rs) / len(rs), 1) if rs else None

    daily: dict[datetime, list[TransferLogRow]] = defaultdict(list)
    for r in rows:  # UTC days, like time_bucket('1 day', …) in the continuous aggregate
        daily[r.departed_at.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)].append(r)

    def grouped(key) -> dict[str, list[TransferLogRow]]:  # noqa: ANN001
        out: dict[str, list[TransferLogRow]] = defaultdict(list)
        for r in rows:
            out[key(r)].append(r)
        return out

    by_hour = grouped(lambda r: f"{r.departed_at.astimezone(zone).hour:02d}")
    return InsightsResponse(
        region_id=region_id, days=days, since=since, source=source, query_ms=query_ms,  # type: ignore[arg-type]
        totals=InsightsTotals(
            transfers=len(rows), seeded=sum(r.seeded for r in rows),
            warning_hours=round(sum(vals(rows, "warning_min")) / 60, 1),
            median_warning_min=median(vals(rows, "warning_min")), median_accept_min=median(vals(rows, "accept_min")),
            p90_accept_min=pctl(vals(rows, "accept_min"), 0.9), median_journey_min=median(vals(rows, "journey_min")),
            prepared_pct=pct_prepared(rows),
        ),
        daily=[
            InsightsDay(day=d, transfers=len(rs), atollcare=sum(r.channel == "atollcare" for r in rs),
                        radio=sum(r.channel == "radio" for r in rs), avg_warning_min=mean(vals(rs, "warning_min")),
                        avg_accept_min=mean(vals(rs, "accept_min")))
            for d, rs in sorted(daily.items())
        ],
        channels=[
            InsightsChannel(channel=c, transfers=len(rs), median_warning_min=median(vals(rs, "warning_min")),  # type: ignore[arg-type]
                            median_accept_min=median(vals(rs, "accept_min")), prepared_pct=pct_prepared(rs))
            for c, rs in sorted(grouped(lambda r: r.channel).items())
        ],
        by_mode=sorted(
            (InsightsGroup(key=k, transfers=len(rs), median_journey_min=median(vals(rs, "journey_min")),
                           median_warning_min=median(vals(rs, "warning_min")))
             for k, rs in grouped(lambda r: r.mode.value).items()),
            key=lambda g: -g.transfers,
        ),
        by_destination=sorted(
            (InsightsGroup(key=k, transfers=len(rs), median_accept_min=median(vals(rs, "accept_min")),
                           median_warning_min=median(vals(rs, "warning_min")))
             for k, rs in grouped(lambda r: r.destination_id).items()),
            key=lambda g: -g.transfers,
        ),
        by_hour=[InsightsGroup(key=f"{h:02d}", transfers=len(by_hour.get(f"{h:02d}", []))) for h in range(24)],
    )
