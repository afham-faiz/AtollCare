# Persistence. PgRepo = TimescaleDB / Tiger Cloud (hypertables + continuous aggregate). MemoryRepo = same interface
# in-process, used by tests and when DATABASE_URL is empty (no-docker dev). The engine owns the database.
from __future__ import annotations

import json
import logging
import re
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

from app.core import insights as insights_mod
from app.models import (
    DemoState,
    InsightsChannel,
    InsightsDay,
    InsightsGroup,
    InsightsResponse,
    InsightsTotals,
    Note,
    Transfer,
    TransferLogRow,
    TrendBucket,
    VitalsReading,
)

log = logging.getLogger("atollcare.db")
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
VITALS_COLS = [
    "transfer_id", "recorded_at", "id", "source", "heart_rate", "resp_rate", "hrv_rmssd", "spo2", "on_oxygen",
    "systolic_bp", "temperature_c", "consciousness", "confidence",
]
LOW_CONFIDENCE = 0.6
DOC_EXCLUDE = {"notes", "vitals"}


def _reading_from_row(row: dict[str, Any]) -> VitalsReading:
    conf = row.get("confidence")
    return VitalsReading(**{k: row.get(k) for k in VITALS_COLS}, low_quality=conf is not None and conf < LOW_CONFIDENCE)


def _avg(rs: list[VitalsReading], attr: str) -> float | None:
    vals = [getattr(r, attr) for r in rs if getattr(r, attr) is not None]
    return sum(vals) / len(vals) if vals else None


class Repo(ABC):
    kind = "abstract"

    async def init(self) -> None: ...

    async def close(self) -> None: ...

    @abstractmethod
    async def ping(self) -> bool: ...

    @abstractmethod
    async def insert_transfer(self, t: Transfer) -> None: ...

    @abstractmethod
    async def update_transfer(self, t: Transfer) -> None: ...

    @abstractmethod
    async def get_transfer(self, transfer_id: UUID) -> Transfer | None:
        """Document only — notes and vitals are loaded separately."""

    @abstractmethod
    async def list_transfers(self) -> list[Transfer]: ...

    @abstractmethod
    async def add_vitals(self, reading: VitalsReading) -> None: ...

    @abstractmethod
    async def get_vitals(self, transfer_id: UUID, limit: int = 120) -> list[VitalsReading]: ...

    @abstractmethod
    async def vitals_trend(self, transfer_id: UUID, since: datetime) -> tuple[list[TrendBucket], str]: ...

    @abstractmethod
    async def add_note(self, note: Note) -> None: ...

    @abstractmethod
    async def get_notes(self, transfer_id: UUID) -> list[Note]: ...

    @abstractmethod
    async def get_demo_state(self) -> DemoState | None: ...

    @abstractmethod
    async def set_demo_state(self, state: DemoState) -> None: ...

    @abstractmethod
    async def reset(self) -> None: ...

    @abstractmethod
    async def versions(self) -> tuple[str | None, str | None]:
        """(timescaledb extension version, server version) — both None for the in-memory store."""

    @abstractmethod
    async def log_transfers(self, rows: list[TransferLogRow]) -> None: ...

    @abstractmethod
    async def clear_seeded(self, region_id: str) -> int: ...

    @abstractmethod
    async def insights(self, region_id: str, days: int, since: datetime, tz: str) -> InsightsResponse: ...


# ---------------------------------------------------------------- in-memory
class MemoryRepo(Repo):
    kind = "memory"

    def __init__(self) -> None:
        self.transfers: dict[UUID, Transfer] = {}
        self.vitals: dict[UUID, list[VitalsReading]] = defaultdict(list)
        self.notes: dict[UUID, list[Note]] = defaultdict(list)
        self.demo: DemoState | None = None
        self.log: dict[UUID, TransferLogRow] = {}

    async def ping(self) -> bool:
        return True

    async def insert_transfer(self, t: Transfer) -> None:
        self.transfers[t.id] = t.model_copy(update={"notes": [], "vitals": []}, deep=True)

    async def update_transfer(self, t: Transfer) -> None:
        await self.insert_transfer(t)

    async def get_transfer(self, transfer_id: UUID) -> Transfer | None:
        t = self.transfers.get(transfer_id)
        return t.model_copy(deep=True) if t else None

    async def list_transfers(self) -> list[Transfer]:
        return [t.model_copy(deep=True) for t in self.transfers.values()]

    async def add_vitals(self, reading: VitalsReading) -> None:
        self.vitals[reading.transfer_id].append(reading)

    async def get_vitals(self, transfer_id: UUID, limit: int = 120) -> list[VitalsReading]:
        return sorted(self.vitals.get(transfer_id, []), key=lambda r: r.recorded_at)[-limit:]

    async def vitals_trend(self, transfer_id: UUID, since: datetime) -> tuple[list[TrendBucket], str]:
        groups: dict[datetime, list[VitalsReading]] = defaultdict(list)
        for r in self.vitals.get(transfer_id, []):
            if r.recorded_at >= since and not r.low_quality:
                groups[r.recorded_at.replace(second=0, microsecond=0)].append(r)
        buckets = [
            TrendBucket(t=t, hr=_avg(rs, "heart_rate"), rr=_avg(rs, "resp_rate"), hrv=_avg(rs, "hrv_rmssd"),
                        spo2=_avg(rs, "spo2"), sbp=_avg(rs, "systolic_bp"), temp=_avg(rs, "temperature_c"))
            for t, rs in sorted(groups.items())
        ]
        return buckets, "memory"

    async def add_note(self, note: Note) -> None:
        self.notes[note.transfer_id].append(note)

    async def get_notes(self, transfer_id: UUID) -> list[Note]:
        return sorted(self.notes.get(transfer_id, []), key=lambda n: n.at)

    async def get_demo_state(self) -> DemoState | None:
        return self.demo.model_copy(deep=True) if self.demo else None

    async def set_demo_state(self, state: DemoState) -> None:
        self.demo = state.model_copy(deep=True)

    async def reset(self) -> None:
        self.transfers.clear()
        self.vitals.clear()
        self.notes.clear()

    async def versions(self) -> tuple[str | None, str | None]:
        return None, None

    async def log_transfers(self, rows: list[TransferLogRow]) -> None:
        for r in rows:
            self.log[r.transfer_id] = r

    async def clear_seeded(self, region_id: str) -> int:
        gone = [k for k, r in self.log.items() if r.seeded and r.region_id == region_id]
        for k in gone:
            del self.log[k]
        return len(gone)

    async def insights(self, region_id: str, days: int, since: datetime, tz: str) -> InsightsResponse:
        t0 = time.perf_counter()
        res = insights_mod.aggregate(list(self.log.values()), region_id, days, since, tz)
        res.query_ms = round((time.perf_counter() - t0) * 1000, 1)
        return res


# ---------------------------------------------------------------- postgres / timescale
def split_sql(sql: str) -> list[str]:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    parts = re.split(r";\s*(?:\n|$)", "\n".join(lines))
    return [p.strip() for p in parts if p.strip()]


TIMESCALE_ONLY = re.compile(r"timescaledb|create_hypertable|add_continuous_aggregate_policy|add_compression_policy", re.I)
LOG_COLS = list(TransferLogRow.model_fields)


def _r(v: Any) -> float | None:
    return round(float(v), 1) if v is not None else None


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
        """Run migrations idempotently, tracking applied files. Statements run outside a transaction (continuous
        aggregates cannot be created inside one). Without timescaledb, Timescale-only statements are skipped and the
        trend query falls back to raw rows."""
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
                    timescale_only = bool(TIMESCALE_ONLY.search(stmt))
                    if not self.timescale and timescale_only:
                        continue
                    try:
                        await conn.execute(stmt)
                    except Exception as exc:  # noqa: BLE001
                        if not timescale_only:
                            raise
                        # an optional Timescale feature (aggregate, policy, compression) must never stop the engine
                        # booting; queries fall back to the raw tables
                        log.warning("%s: skipped Timescale statement (%s): %s", path.name, exc, stmt.splitlines()[0])
                await conn.execute("INSERT INTO schema_migrations (filename) VALUES ($1)", path.name)
                log.info("applied migration %s", path.name)
            if self.timescale:
                self.timescale = bool(await conn.fetchval("SELECT to_regclass('vitals_1m') IS NOT NULL"))

    async def ping(self) -> bool:
        try:
            async with self.pool.acquire() as conn:
                return await conn.fetchval("SELECT 1") == 1
        except Exception:  # noqa: BLE001
            return False

    def _doc(self, t: Transfer) -> dict[str, Any]:
        return t.model_dump(mode="json", exclude=DOC_EXCLUDE)

    async def insert_transfer(self, t: Transfer) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO transfers (id, code, region_id, status, created_at, updated_at, doc) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                t.id, t.code, t.region_id, t.status.value, t.created_at, t.updated_at, self._doc(t),
            )

    async def update_transfer(self, t: Transfer) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "UPDATE transfers SET status=$2, updated_at=$3, doc=$4 WHERE id=$1",
                t.id, t.status.value, t.updated_at, self._doc(t),
            )

    async def get_transfer(self, transfer_id: UUID) -> Transfer | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT doc FROM transfers WHERE id=$1", transfer_id)
        return Transfer.model_validate(row["doc"]) if row else None

    async def list_transfers(self) -> list[Transfer]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT doc FROM transfers ORDER BY updated_at DESC LIMIT 200")
        return [Transfer.model_validate(r["doc"]) for r in rows]

    async def add_vitals(self, reading: VitalsReading) -> None:
        values = [getattr(reading, c) for c in VITALS_COLS]
        values = [v.value if hasattr(v, "value") else v for v in values]
        ph = ", ".join(f"${i + 1}" for i in range(len(VITALS_COLS)))
        async with self.pool.acquire() as conn:
            await conn.execute(f"INSERT INTO vitals_readings ({', '.join(VITALS_COLS)}) VALUES ({ph})", *values)

    async def get_vitals(self, transfer_id: UUID, limit: int = 120) -> list[VitalsReading]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                f"SELECT {', '.join(VITALS_COLS)} FROM vitals_readings WHERE transfer_id=$1 "
                "ORDER BY recorded_at DESC LIMIT $2",
                transfer_id, limit,
            )
        return [_reading_from_row(dict(r)) for r in reversed(rows)]

    async def vitals_trend(self, transfer_id: UUID, since: datetime) -> tuple[list[TrendBucket], str]:
        async with self.pool.acquire() as conn:
            if self.timescale:
                rows = await conn.fetch(
                    "SELECT bucket AS t, hr, rr, hrv, spo2, sbp, temp FROM vitals_1m "
                    "WHERE transfer_id=$1 AND bucket >= $2 ORDER BY bucket",
                    transfer_id, since,
                )
                if rows:
                    return [TrendBucket(**dict(r)) for r in rows], "vitals_1m"
            rows = await conn.fetch(
                """SELECT date_trunc('minute', recorded_at) AS t, avg(heart_rate) AS hr, avg(resp_rate) AS rr,
                          avg(hrv_rmssd) AS hrv, avg(spo2) AS spo2, avg(systolic_bp) AS sbp, avg(temperature_c) AS temp
                   FROM vitals_readings WHERE transfer_id=$1 AND recorded_at >= $2
                     AND (confidence IS NULL OR confidence >= $3)
                   GROUP BY 1 ORDER BY 1""",
                transfer_id, since, LOW_CONFIDENCE,
            )
        return [TrendBucket(**dict(r)) for r in rows], "raw"

    async def add_note(self, note: Note) -> None:
        data = note.model_dump(mode="json", include={"reply_to", "extraction", "extracted_by", "audio_url"})
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO transfer_notes (transfer_id, at, id, author, kind, text, data) VALUES ($1,$2,$3,$4,$5,$6,$7)",
                note.transfer_id, note.at, note.id, note.author.value, note.kind.value, note.text, data,
            )

    async def get_notes(self, transfer_id: UUID) -> list[Note]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT * FROM transfer_notes WHERE transfer_id=$1 ORDER BY at, id", transfer_id)
        out: list[Note] = []
        for r in rows:
            d = dict(r)
            data = d.pop("data") or {}
            out.append(Note(**d, **data))
        return out

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

    async def reset(self) -> None:
        # rows only — never drop tables. The transfer log (network history) is kept.
        async with self.pool.acquire() as conn:
            for table in ("vitals_readings", "transfer_notes", "transfers"):
                await conn.execute(f"DELETE FROM {table}")

    async def versions(self) -> tuple[str | None, str | None]:
        async with self.pool.acquire() as conn:
            ts = await conn.fetchval("SELECT extversion FROM pg_extension WHERE extname='timescaledb'")
            server = await conn.fetchval("SHOW server_version")
        return ts, server

    async def log_transfers(self, rows: list[TransferLogRow]) -> None:
        if not rows:
            return
        records = [tuple(getattr(r, c).value if c == "mode" else getattr(r, c) for c in LOG_COLS) for r in rows]
        async with self.pool.acquire() as conn:
            # upsert so a live transfer logged at arrival and again at close keeps one row
            await conn.executemany(
                f"INSERT INTO transfer_log ({', '.join(LOG_COLS)}) VALUES ({', '.join(f'${i + 1}' for i in range(len(LOG_COLS)))}) "
                "ON CONFLICT (transfer_id, departed_at) DO UPDATE SET "
                + ", ".join(f"{c}=EXCLUDED.{c}" for c in LOG_COLS if c not in ("transfer_id", "departed_at")),
                records,
            )
        await self._refresh_daily(min(r.departed_at for r in rows))

    async def clear_seeded(self, region_id: str) -> int:
        async with self.pool.acquire() as conn:
            first = await conn.fetchval("SELECT min(departed_at) FROM transfer_log WHERE seeded AND region_id=$1", region_id)
            status = await conn.execute("DELETE FROM transfer_log WHERE seeded AND region_id=$1", region_id)
        if first:
            await self._refresh_daily(first)
        return int(status.split()[-1])

    async def _refresh_daily(self, since: datetime) -> None:
        """Back-filled history lands below the aggregate's watermark; refresh that window so the daily series (and
        totals after a re-seed) are right immediately instead of after the next policy run."""
        if not self.timescale:
            return
        try:
            start = (since - timedelta(days=1)).isoformat()  # our own datetime, not user input
            async with self.pool.acquire() as conn:
                # simple-query protocol (no bind params): CALL must not run inside a transaction block
                await conn.execute(f"CALL refresh_continuous_aggregate('transfer_daily', '{start}'::timestamptz, NULL)")
        except Exception as exc:  # noqa: BLE001 — the raw fallback still answers
            log.warning("transfer_daily refresh failed: %s", exc)

    async def insights(self, region_id: str, days: int, since: datetime, tz: str) -> InsightsResponse:
        t0 = time.perf_counter()
        where = "FROM transfer_log WHERE region_id=$1 AND departed_at >= $2"
        p50 = "percentile_cont(0.5) WITHIN GROUP (ORDER BY {})"
        async with self.pool.acquire() as conn:
            tot = await conn.fetchrow(
                f"""SELECT count(*) AS transfers, count(*) FILTER (WHERE seeded) AS seeded,
                           coalesce(sum(warning_min), 0) / 60 AS warning_hours,
                           {p50.format('warning_min')} AS median_warning_min, {p50.format('accept_min')} AS median_accept_min,
                           percentile_cont(0.9) WITHIN GROUP (ORDER BY accept_min) AS p90_accept_min,
                           {p50.format('journey_min')} AS median_journey_min,
                           100.0 * avg(prepared::int) AS prepared_pct
                    {where}""",
                region_id, since,
            )
            source = "raw"
            daily_rows: list[Any] = []
            if self.timescale and await conn.fetchval("SELECT to_regclass('transfer_daily') IS NOT NULL"):
                daily_rows = await conn.fetch(
                    """SELECT day, sum(transfers)::int AS transfers,
                              coalesce(sum(transfers) FILTER (WHERE channel='atollcare'), 0)::int AS atollcare,
                              coalesce(sum(transfers) FILTER (WHERE channel='radio'), 0)::int AS radio,
                              sum(sum_warning_min) / nullif(sum(n_warning), 0) AS avg_warning_min,
                              sum(sum_accept_min) / nullif(sum(n_accept), 0) AS avg_accept_min
                       FROM transfer_daily WHERE region_id=$1 AND day >= $2 GROUP BY day ORDER BY day""",
                    region_id, since - timedelta(days=1),
                )
                daily_rows = [r for r in daily_rows if r["day"] >= since.replace(hour=0, minute=0, second=0, microsecond=0)]
                source = "transfer_daily"
            if source == "raw":
                daily_rows = await conn.fetch(
                    f"""SELECT date_trunc('day', departed_at AT TIME ZONE 'UTC') AT TIME ZONE 'UTC' AS day,
                               count(*)::int AS transfers,
                               count(*) FILTER (WHERE channel='atollcare')::int AS atollcare,
                               count(*) FILTER (WHERE channel='radio')::int AS radio,
                               avg(warning_min) AS avg_warning_min, avg(accept_min) AS avg_accept_min
                        {where} GROUP BY 1 ORDER BY 1""",
                    region_id, since,
                )
            channels = await conn.fetch(
                f"""SELECT channel, count(*)::int AS transfers, {p50.format('warning_min')} AS w,
                           {p50.format('accept_min')} AS a, 100.0 * avg(prepared::int) AS p
                    {where} GROUP BY channel ORDER BY channel""",
                region_id, since,
            )
            modes = await conn.fetch(
                f"""SELECT mode AS key, count(*)::int AS transfers, {p50.format('journey_min')} AS j,
                           {p50.format('warning_min')} AS w {where} GROUP BY mode ORDER BY 2 DESC""",
                region_id, since,
            )
            dests = await conn.fetch(
                f"""SELECT destination_id AS key, count(*)::int AS transfers, {p50.format('accept_min')} AS a,
                           {p50.format('warning_min')} AS w {where} GROUP BY destination_id ORDER BY 2 DESC""",
                region_id, since,
            )
            hours = await conn.fetch(
                f"""SELECT extract(hour FROM departed_at AT TIME ZONE $3)::int AS h, count(*)::int AS transfers
                    {where} GROUP BY 1""",
                region_id, since, tz,
            )
        per_hour = {r["h"]: r["transfers"] for r in hours}
        return InsightsResponse(
            region_id=region_id, days=days, since=since, source=source,  # type: ignore[arg-type]
            query_ms=round((time.perf_counter() - t0) * 1000, 1),
            totals=InsightsTotals(
                transfers=tot["transfers"], seeded=tot["seeded"], warning_hours=_r(tot["warning_hours"]) or 0.0,
                median_warning_min=_r(tot["median_warning_min"]), median_accept_min=_r(tot["median_accept_min"]),
                p90_accept_min=_r(tot["p90_accept_min"]), median_journey_min=_r(tot["median_journey_min"]),
                prepared_pct=_r(tot["prepared_pct"]),
            ),
            daily=[InsightsDay(day=r["day"], transfers=r["transfers"], atollcare=r["atollcare"], radio=r["radio"],
                               avg_warning_min=_r(r["avg_warning_min"]), avg_accept_min=_r(r["avg_accept_min"]))
                   for r in daily_rows],
            channels=[InsightsChannel(channel=r["channel"], transfers=r["transfers"], median_warning_min=_r(r["w"]),
                                      median_accept_min=_r(r["a"]), prepared_pct=_r(r["p"])) for r in channels],
            by_mode=[InsightsGroup(key=r["key"], transfers=r["transfers"], median_journey_min=_r(r["j"]),
                                   median_warning_min=_r(r["w"])) for r in modes],
            by_destination=[InsightsGroup(key=r["key"], transfers=r["transfers"], median_accept_min=_r(r["a"]),
                                          median_warning_min=_r(r["w"])) for r in dests],
            by_hour=[InsightsGroup(key=f"{h:02d}", transfers=per_hour.get(h, 0)) for h in range(24)],
        )


def make_repo(database_url: str, use_memory: bool) -> Repo:
    if use_memory:
        return MemoryRepo()
    return PgRepo(database_url.replace("postgresql+asyncpg://", "postgresql://"))
