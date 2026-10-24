# F-M7.2 Persistence. PgRepo = TimescaleDB / Tiger Cloud (hypertables + continuous aggregate). MemoryRepo = same
# interface in-process, used by tests and when DATABASE_URL is empty (no-docker dev). The engine owns the DB.
from __future__ import annotations

import json
import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from app.models import (
    Case,
    CaseEvent,
    CaseHeadline,
    DemoState,
    HospitalCapacity,
    TrackPoint,
    TransportAsset,
    TrendBucket,
    VitalsReading,
)

log = logging.getLogger("atollcare.db")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
CASE_JSON_COLS = ["patient", "intake", "news2", "recommendation", "referral", "transport", "meta"]
VITALS_COLS = [
    "case_id", "recorded_at", "id", "source", "heart_rate", "resp_rate", "spo2", "on_oxygen", "systolic_bp",
    "temperature_c", "consciousness", "confidence", "media_url",
]
LOW_CONFIDENCE = 0.6
EMPTY_HEADLINE = CaseHeadline(elapsed_min=0, projected_total_min=None, saved_vs_baseline_min=None, text="")


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return value


def _vitals_from_row(row: dict[str, Any]) -> VitalsReading:
    conf = row.get("confidence")
    return VitalsReading(**{k: row.get(k) for k in VITALS_COLS}, low_quality=conf is not None and conf < LOW_CONFIDENCE)


class Repo(ABC):
    kind = "abstract"

    async def init(self) -> None: ...

    async def close(self) -> None: ...

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def insert_case(self, case: Case) -> None: ...

    @abstractmethod
    async def update_case(self, case: Case) -> None: ...

    @abstractmethod
    async def get_case(self, case_id: UUID, vitals_limit: int = 50) -> Case | None: ...

    @abstractmethod
    async def list_cases(self) -> list[Case]: ...

    @abstractmethod
    async def add_vitals(self, reading: VitalsReading) -> None: ...

    @abstractmethod
    async def get_vitals(self, case_id: UUID, limit: int = 50) -> list[VitalsReading]: ...

    @abstractmethod
    async def vitals_trend(self, case_id: UUID, since: datetime) -> tuple[list[TrendBucket], str]: ...

    @abstractmethod
    async def add_event(self, event: CaseEvent) -> None: ...

    @abstractmethod
    async def get_events(self, case_id: UUID) -> list[CaseEvent]: ...

    @abstractmethod
    async def add_position(self, case_id: UUID, point: TrackPoint, asset_id: str | None, speed_kmh: float | None) -> None: ...

    @abstractmethod
    async def get_positions(self, case_id: UUID) -> list[TrackPoint]: ...

    @abstractmethod
    async def list_assets(self) -> list[TransportAsset]: ...

    @abstractmethod
    async def upsert_asset(self, asset: TransportAsset) -> None: ...

    @abstractmethod
    async def list_capacity(self) -> list[HospitalCapacity]: ...

    @abstractmethod
    async def upsert_capacity(self, cap: HospitalCapacity) -> None: ...

    @abstractmethod
    async def get_demo_state(self) -> DemoState | None: ...

    @abstractmethod
    async def set_demo_state(self, state: DemoState) -> None: ...

    @abstractmethod
    async def reset_cases(self) -> None: ...


# ---------------------------------------------------------------- in-memory
class MemoryRepo(Repo):
    kind = "memory"

    def __init__(self) -> None:
        self.cases: dict[UUID, Case] = {}
        self.vitals: dict[UUID, list[VitalsReading]] = defaultdict(list)
        self.events: dict[UUID, list[CaseEvent]] = defaultdict(list)
        self.positions: dict[UUID, list[TrackPoint]] = defaultdict(list)
        self.assets: dict[str, TransportAsset] = {}
        self.capacity: dict[str, HospitalCapacity] = {}
        self.demo: DemoState | None = None

    async def ping(self) -> bool:
        return True

    async def insert_case(self, case: Case) -> None:
        self.cases[case.id] = case.model_copy(update={"vitals": [], "timeline": []}, deep=True)

    async def update_case(self, case: Case) -> None:
        await self.insert_case(case)

    async def get_case(self, case_id: UUID, vitals_limit: int = 50) -> Case | None:
        case = self.cases.get(case_id)
        if case is None:
            return None
        return case.model_copy(
            update={"vitals": await self.get_vitals(case_id, vitals_limit), "timeline": await self.get_events(case_id)},
            deep=True,
        )

    async def list_cases(self) -> list[Case]:
        return [c.model_copy(deep=True) for c in self.cases.values()]

    async def add_vitals(self, reading: VitalsReading) -> None:
        self.vitals[reading.case_id].append(reading)

    async def get_vitals(self, case_id: UUID, limit: int = 50) -> list[VitalsReading]:
        return sorted(self.vitals.get(case_id, []), key=lambda r: r.recorded_at)[-limit:]

    async def vitals_trend(self, case_id: UUID, since: datetime) -> tuple[list[TrendBucket], str]:
        groups: dict[datetime, list[VitalsReading]] = defaultdict(list)
        for r in self.vitals.get(case_id, []):
            if r.recorded_at >= since and not r.low_quality:
                groups[r.recorded_at.replace(second=0, microsecond=0)].append(r)

        def avg(rs: list[VitalsReading], attr: str) -> float | None:
            vals = [getattr(r, attr) for r in rs if getattr(r, attr) is not None]
            return sum(vals) / len(vals) if vals else None

        buckets = [
            TrendBucket(t=t, hr=avg(rs, "heart_rate"), rr=avg(rs, "resp_rate"), spo2=avg(rs, "spo2"),
                        sbp=avg(rs, "systolic_bp"), temp=avg(rs, "temperature_c"))
            for t, rs in sorted(groups.items())
        ]
        return buckets, "memory"

    async def add_event(self, event: CaseEvent) -> None:
        self.events[event.case_id].append(event)

    async def get_events(self, case_id: UUID) -> list[CaseEvent]:
        return sorted(self.events.get(case_id, []), key=lambda e: e.at)

    async def add_position(self, case_id: UUID, point: TrackPoint, asset_id: str | None, speed_kmh: float | None) -> None:
        pts = self.positions[case_id]
        if pts and pts[-1].t == point.t:
            return
        pts.append(point)

    async def get_positions(self, case_id: UUID) -> list[TrackPoint]:
        return list(self.positions.get(case_id, []))

    async def list_assets(self) -> list[TransportAsset]:
        return [a.model_copy() for a in self.assets.values()]

    async def upsert_asset(self, asset: TransportAsset) -> None:
        self.assets[asset.id] = asset.model_copy()

    async def list_capacity(self) -> list[HospitalCapacity]:
        return [c.model_copy() for c in self.capacity.values()]

    async def upsert_capacity(self, cap: HospitalCapacity) -> None:
        self.capacity[cap.facility_id] = cap.model_copy()

    async def get_demo_state(self) -> DemoState | None:
        return self.demo.model_copy(deep=True) if self.demo else None

    async def set_demo_state(self, state: DemoState) -> None:
        self.demo = state.model_copy(deep=True)

    async def reset_cases(self) -> None:
        self.cases.clear()
        self.vitals.clear()
        self.events.clear()
        self.positions.clear()


# ---------------------------------------------------------------- postgres / timescale
def split_sql(sql: str) -> list[str]:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    parts = re.split(r";\s*(?:\n|$)", "\n".join(lines))
    return [p.strip() for p in parts if p.strip()]


TIMESCALE_ONLY = re.compile(r"timescaledb|create_hypertable|add_continuous_aggregate_policy", re.I)


class PgRepo(Repo):
    kind = "postgres"

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn
        self.pool: Any = None
        self.timescale = False

    async def _init_conn(self, conn: Any) -> None:
        await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")

    async def init(self) -> None:
        import asyncpg

        self.pool = await asyncpg.create_pool(self.dsn, min_size=1, max_size=8, init=self._init_conn)
        await self.migrate()

    async def close(self) -> None:
        if self.pool:
            await self.pool.close()

    async def migrate(self) -> None:
        """Run migrations idempotently, tracking applied files. Each statement runs outside a transaction (continuous
        aggregates cannot be created inside one). Without the timescaledb extension, Timescale-only statements are
        skipped and the trend query falls back to raw rows."""
        async with self.pool.acquire() as conn:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())"
            )
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS timescaledb")
                self.timescale = True
            except Exception as exc:  # noqa: BLE001
                log.warning("timescaledb extension unavailable (%s) — running on plain Postgres", exc)
            applied = {r["filename"] for r in await conn.fetch("SELECT filename FROM schema_migrations")}
            for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
                if path.name in applied:
                    continue
                for stmt in split_sql(path.read_text(encoding="utf-8")):
                    if not self.timescale and TIMESCALE_ONLY.search(stmt):
                        continue
                    await conn.execute(stmt)
                await conn.execute("INSERT INTO schema_migrations (filename) VALUES ($1)", path.name)
                log.info("applied migration %s", path.name)
            if self.timescale:
                has_view = await conn.fetchval("SELECT to_regclass('vitals_1m') IS NOT NULL")
                self.timescale = bool(has_view)

    async def ping(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1
        except Exception:  # noqa: BLE001
            return False

    def _case_params(self, case: Case) -> list[Any]:
        return [
            case.id, case.short_code, case.created_at, case.updated_at, case.status.value, case.origin_facility_id,
            *[_jsonable(getattr(case, c)) for c in CASE_JSON_COLS],
        ]

    async def insert_case(self, case: Case) -> None:
        cols = ["id", "short_code", "created_at", "updated_at", "status", "origin_facility_id", *CASE_JSON_COLS]
        ph = ", ".join(f"${i + 1}" for i in range(len(cols)))
        async with self.pool.acquire() as conn:
            await conn.execute(f"INSERT INTO cases ({', '.join(cols)}) VALUES ({ph})", *self._case_params(case))

    async def update_case(self, case: Case) -> None:
        sets = ["updated_at=$4", "status=$5", "origin_facility_id=$6"] + [
            f"{c}=${i + 7}" for i, c in enumerate(CASE_JSON_COLS)
        ]
        async with self.pool.acquire() as conn:
            await conn.execute(
                f"UPDATE cases SET {', '.join(sets)} WHERE id=$1 AND short_code=$2 AND created_at=$3",
                *self._case_params(case),
            )

    def _case_from_row(self, row: Any) -> Case:
        data = dict(row)
        fac = data["origin_facility_id"]
        from app.core import refdata

        f = refdata.facility(fac)
        data["origin_point"] = {"lat": f.lat, "lng": f.lng} if f else {"lat": 0, "lng": 0}
        data["headline"] = EMPTY_HEADLINE
        data["transport"] = data.get("transport") or {"status": "none"}
        data["meta"] = data.get("meta") or {}
        return Case.model_validate(data)

    async def get_case(self, case_id: UUID, vitals_limit: int = 50) -> Case | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM cases WHERE id=$1", case_id)
        if row is None:
            return None
        case = self._case_from_row(row)
        case.vitals = await self.get_vitals(case_id, vitals_limit)
        case.timeline = await self.get_events(case_id)
        return case

    async def list_cases(self) -> list[Case]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM cases ORDER BY updated_at DESC LIMIT 200")
        return [self._case_from_row(r) for r in rows]

    async def add_vitals(self, reading: VitalsReading) -> None:
        values = [getattr(reading, c) for c in VITALS_COLS]
        values = [v.value if hasattr(v, "value") else v for v in values]
        ph = ", ".join(f"${i + 1}" for i in range(len(VITALS_COLS)))
        async with self.pool.acquire() as conn:
            await conn.execute(f"INSERT INTO vitals_readings ({', '.join(VITALS_COLS)}) VALUES ({ph})", *values)

    async def get_vitals(self, case_id: UUID, limit: int = 50) -> list[VitalsReading]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {', '.join(VITALS_COLS)} FROM vitals_readings WHERE case_id=$1 ORDER BY recorded_at DESC LIMIT $2",
                case_id, limit,
            )
        return [_vitals_from_row(dict(r)) for r in reversed(rows)]

    async def vitals_trend(self, case_id: UUID, since: datetime) -> tuple[list[TrendBucket], str]:
        async with self.pool.acquire() as conn:
            if self.timescale:
                rows = await conn.fetch(
                    "SELECT bucket AS t, hr, rr, spo2, sbp, temp FROM vitals_1m WHERE case_id=$1 AND bucket >= $2 ORDER BY bucket",
                    case_id, since,
                )
                if rows:
                    return [TrendBucket(**dict(r)) for r in rows], "vitals_1m"
            rows = await conn.fetch(
                """SELECT date_trunc('minute', recorded_at) AS t, avg(heart_rate) AS hr, avg(resp_rate) AS rr,
                          avg(spo2) AS spo2, avg(systolic_bp) AS sbp, avg(temperature_c) AS temp
                   FROM vitals_readings WHERE case_id=$1 AND recorded_at >= $2
                     AND (confidence IS NULL OR confidence >= $3)
                   GROUP BY 1 ORDER BY 1""",
                case_id, since, LOW_CONFIDENCE,
            )
        return [TrendBucket(**dict(r)) for r in rows], "raw"

    async def add_event(self, event: CaseEvent) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO case_events (case_id, at, id, type, actor_role, summary, data) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                event.case_id, event.at, event.id, event.type.value, event.actor_role, event.summary,
                json.loads(json.dumps(event.data, default=str)),
            )

    async def get_events(self, case_id: UUID) -> list[CaseEvent]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM case_events WHERE case_id=$1 ORDER BY at, id", case_id)
        return [CaseEvent(**dict(r)) for r in rows]

    async def add_position(self, case_id: UUID, point: TrackPoint, asset_id: str | None, speed_kmh: float | None) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO transport_positions (case_id, recorded_at, asset_id, leg_index, lat, lng, speed_kmh)
                   VALUES ($1,$2,$3,$4,$5,$6,$7) ON CONFLICT DO NOTHING""",
                case_id, point.t, asset_id, point.leg_index, point.lat, point.lng, speed_kmh,
            )

    async def get_positions(self, case_id: UUID) -> list[TrackPoint]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT recorded_at AS t, lat, lng, leg_index FROM transport_positions WHERE case_id=$1 ORDER BY recorded_at",
                case_id,
            )
        return [TrackPoint(**dict(r)) for r in rows]

    async def list_assets(self) -> list[TransportAsset]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM transport_assets ORDER BY id")
        return [TransportAsset(**dict(r)) for r in rows]

    async def upsert_asset(self, asset: TransportAsset) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO transport_assets (id, mode, home_facility_id, status, crew_note) VALUES ($1,$2,$3,$4,$5)
                   ON CONFLICT (id) DO UPDATE SET mode=EXCLUDED.mode, home_facility_id=EXCLUDED.home_facility_id,
                   status=EXCLUDED.status, crew_note=EXCLUDED.crew_note""",
                asset.id, asset.mode.value, asset.home_facility_id, asset.status, asset.crew_note,
            )

    async def list_capacity(self) -> list[HospitalCapacity]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM hospital_capacity ORDER BY facility_id")
        return [HospitalCapacity(**dict(r)) for r in rows]

    async def upsert_capacity(self, cap: HospitalCapacity) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """INSERT INTO hospital_capacity (facility_id, icu_beds_free, cath_lab_available, ct_available,
                   blood_bank_units, updated_at) VALUES ($1,$2,$3,$4,$5,$6)
                   ON CONFLICT (facility_id) DO UPDATE SET icu_beds_free=EXCLUDED.icu_beds_free,
                   cath_lab_available=EXCLUDED.cath_lab_available, ct_available=EXCLUDED.ct_available,
                   blood_bank_units=EXCLUDED.blood_bank_units, updated_at=EXCLUDED.updated_at""",
                cap.facility_id, cap.icu_beds_free, cap.cath_lab_available, cap.ct_available, cap.blood_bank_units,
                cap.updated_at,
            )

    async def get_demo_state(self) -> DemoState | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT state FROM demo_state WHERE id=1")
        return DemoState.model_validate(row["state"]) if row else None

    async def set_demo_state(self, state: DemoState) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO demo_state (id, state) VALUES (1, $1) ON CONFLICT (id) DO UPDATE SET state=EXCLUDED.state",
                state.model_dump(mode="json"),
            )

    async def reset_cases(self) -> None:
        # rows only — never drop tables (§6.3)
        async with self.pool.acquire() as conn:
            for table in ("transport_positions", "vitals_readings", "case_events", "cases"):
                await conn.execute(f"DELETE FROM {table}")


def make_repo(database_url: str, use_memory: bool) -> Repo:
    if use_memory:
        return MemoryRepo()
    dsn = database_url.replace("postgresql+asyncpg://", "postgresql://")
    return PgRepo(dsn)
