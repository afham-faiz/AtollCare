# Persistence. PgRepo = TimescaleDB / Tiger Cloud (hypertables + continuous aggregate). MemoryRepo = same interface
# in-process, used by tests and when DATABASE_URL is empty (no-docker dev). The engine owns the database.
from __future__ import annotations

import asyncio
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

from app.models import DemoState, Note, Transfer, TrendBucket, VitalsReading

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
    async def vitals_trend(self, transfer_id: UUID, since: datetime) -> tuple[list[TrendBucket], str]:
        """1-minute buckets of measured readings only (Presage, crew); simulated and low-confidence rows excluded."""

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

    # ---- network analytics (Tiger Data only; the in-memory store has no history to analyse)
    async def database_info(self) -> tuple[str, str | None]:
        return "In-memory", None

    async def insights(self, days: int) -> dict[str, Any] | None:
        return None

    async def benchmark(self, days: int) -> dict[str, Any] | None:
        return None

    async def seed_history(self, days: int, per_day: int, region_id: str, origins: list[str], destinations: list[str],
                           modes: list[str]) -> dict[str, Any] | None:
        return None


# ---------------------------------------------------------------- in-memory
class MemoryRepo(Repo):
    kind = "memory"

    def __init__(self) -> None:
        self.transfers: dict[UUID, Transfer] = {}
        self.vitals: dict[UUID, list[VitalsReading]] = defaultdict(list)
        self.notes: dict[UUID, list[Note]] = defaultdict(list)
        self.demo: DemoState | None = None

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
            if r.recorded_at >= since and not r.low_quality and r.source != "simulated":
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


# ---------------------------------------------------------------- postgres / timescale
def split_sql(sql: str) -> list[str]:
    lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
    parts = re.split(r";\s*(?:\n|$)", "\n".join(lines))
    return [p.strip() for p in parts if p.strip()]


TIMESCALE_ONLY = re.compile(
    r"timescaledb|create_hypertable|add_continuous_aggregate_policy|add_compression_policy|set_chunk_time_interval",
    re.IGNORECASE,
)


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
                    if not self.timescale and TIMESCALE_ONLY.search(stmt):
                        continue
                    await conn.execute(stmt)
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
            rows = await conn.fetch("SELECT doc FROM transfers WHERE NOT seeded ORDER BY updated_at DESC LIMIT 200")
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
                     AND (confidence IS NULL OR confidence >= $3) AND source <> 'simulated'
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
        # live demo rows only — seeded network history stays; their readings and notes go with them (ON DELETE CASCADE)
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM transfers WHERE NOT seeded")


    # ---------------------------------------------------------------- network analytics
    async def database_info(self) -> tuple[str, str | None]:
        async with self.pool.acquire() as conn:
            version = await conn.fetchval("SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'")
        if version is None:
            return "PostgreSQL", None
        # Tiger Cloud service hosts end in tsdb.cloud.timescale.com
        return ("Tiger Cloud" if "timescale.com" in self.dsn else "TimescaleDB"), version

    async def insights(self, days: int) -> dict[str, Any] | None:
        if not self.timescale:
            return None
        timed: list[dict[str, Any]] = []

        async def q(conn: Any, name: str, source: str, sql: str, *args: Any) -> list[Any]:
            t0 = time.perf_counter()
            rows = await conn.fetch(sql, *args)
            timed.append({"name": name, "source": source, "ms": round((time.perf_counter() - t0) * 1000, 1)})
            return rows

        window = timedelta(days=days)
        async with self.pool.acquire() as conn:
            kpis = (await q(conn, "Transfer outcomes", "transfers (relational)", """
                WITH t AS (
                  SELECT seeded, (doc->>'handoff_at')::timestamptz AS handoff, (doc->'acceptance'->>'at')::timestamptz AS accepted,
                         (doc->>'departed_at')::timestamptz AS departed, (doc->>'arrived_at')::timestamptz AS arrived,
                         (doc->'news2'->>'total')::int AS news2
                  FROM transfers WHERE created_at >= now() - $1::interval)
                SELECT count(*) AS transfers, count(handoff) AS handed_off, count(accepted) AS accepted,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM accepted - handoff) / 60) AS median_accept,
                       percentile_cont(0.9) WITHIN GROUP (ORDER BY extract(epoch FROM accepted - handoff) / 60) AS p90_accept,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM arrived - departed) / 60) AS median_journey,
                       count(*) FILTER (WHERE news2 >= 7) AS high_risk,
                       count(*) FILTER (WHERE seeded) AS seeded, count(*) FILTER (WHERE NOT seeded) AS live
                FROM t""", window))[0]
            per_day = await q(conn, "Transfers per day", "transfers (relational)", """
                SELECT time_bucket('1 day', created_at) AS day, count(*) AS n
                FROM transfers WHERE created_at >= now() - $1::interval GROUP BY 1""", window)
            events = await q(conn, "Alerts and questions per day", "network_events_1d (continuous aggregate)", """
                SELECT bucket AS day, kind, n FROM network_events_1d
                WHERE bucket >= now() - $1::interval AND kind IN ('alert', 'question')""", window)
            readings = await q(conn, "Vitals readings per day", "network_vitals_1h (continuous aggregate)", """
                SELECT time_bucket('1 day', bucket) AS day, sum(readings)::bigint AS n FROM network_vitals_1h
                WHERE bucket >= now() - $1::interval GROUP BY 1""", window)
            destinations = await q(conn, "Time to acceptance by hospital", "transfers (relational)", """
                SELECT doc->>'destination_id' AS destination_id, count(*) AS n,
                       percentile_cont(0.5) WITHIN GROUP (ORDER BY extract(epoch FROM
                         (doc->'acceptance'->>'at')::timestamptz - (doc->>'handoff_at')::timestamptz) / 60) AS median_accept
                FROM transfers WHERE created_at >= now() - $1::interval AND doc->>'handoff_at' IS NOT NULL
                GROUP BY 1 ORDER BY median_accept DESC NULLS LAST""", window)  # slowest first: where to act
            storage = []
            for table in ("vitals_readings", "transfer_notes"):
                # exact: approximate_row_count can't see inside compressed chunks, and counting columnar batches is cheap
                rows = await conn.fetchval(f"SELECT count(*) FROM {table}")
                chunks = await conn.fetchrow(
                    "SELECT count(*) AS n, count(*) FILTER (WHERE is_compressed) AS compressed "
                    "FROM timescaledb_information.chunks WHERE hypertable_name = $1", table)
                comp = await conn.fetchrow(
                    "SELECT sum(before_compression_total_bytes)::bigint AS before, "
                    "sum(after_compression_total_bytes)::bigint AS after FROM hypertable_compression_stats($1::regclass)", table)
                storage.append({
                    "name": table, "rows": int(rows or 0), "chunks": chunks["n"], "compressed_chunks": chunks["compressed"],
                    "bytes_before_compression": comp["before"], "bytes_after_compression": comp["after"],
                    "total_bytes": await conn.fetchval("SELECT hypertable_size($1::regclass)", table),
                })
            aggregates = [r["view_name"] for r in await conn.fetch(
                "SELECT view_name FROM timescaledb_information.continuous_aggregates ORDER BY view_name")]
        return {"kpis": kpis, "per_day": per_day, "events": events, "readings": readings, "destinations": destinations,
                "storage": storage, "aggregates": aggregates, "queries": timed}

    async def benchmark(self, days: int) -> dict[str, Any] | None:
        """The same question asked of the continuous aggregate and of the raw hypertable; median of three runs each."""
        if not self.timescale:
            return None
        window = timedelta(days=days)
        agg_sql = ("SELECT bucket, sum(readings) AS n FROM network_vitals_1h WHERE bucket >= now() - $1::interval "
                   "GROUP BY bucket ORDER BY bucket")
        raw_sql = ("SELECT time_bucket('1 hour', recorded_at) AS bucket, count(*) AS n FROM vitals_readings "
                   "WHERE recorded_at >= now() - $1::interval GROUP BY 1 ORDER BY 1")

        async def median_ms(conn: Any, sql: str) -> tuple[float, list[Any]]:
            runs, rows = [], []
            for _ in range(3):
                t0 = time.perf_counter()
                rows = await conn.fetch(sql, window)
                runs.append((time.perf_counter() - t0) * 1000)
            return sorted(runs)[1], rows

        async with self.pool.acquire() as conn:
            raw_ms, raw_rows = await median_ms(conn, raw_sql)
            agg_ms, _ = await median_ms(conn, agg_sql)
        return {"aggregate_ms": round(agg_ms, 1), "raw_ms": round(raw_ms, 1), "rows_scanned": sum(r["n"] for r in raw_rows)}

    @staticmethod
    async def _refresh_aggregate(conn: Any, view: str) -> None:
        """Materialise a continuous aggregate now. If Tiger's own refresh policy is mid-run, wait briefly and retry —
        and if it stays busy, carry on: real-time aggregation already includes rows not yet materialised."""
        import asyncpg

        for attempt in range(6):
            try:
                await conn.execute(f"CALL refresh_continuous_aggregate('{view}', NULL, NULL)")
                return
            except asyncpg.exceptions.LockNotAvailableError:
                await asyncio.sleep(0.5 * (attempt + 1))
        log.info("refresh of %s left to its policy job (still busy)", view)

    async def seed_history(self, days: int, per_day: int, region_id: str, origins: list[str], destinations: list[str],
                           modes: list[str]) -> dict[str, Any] | None:
        """Generate `days` of simulated transfer history server-side (generate_series), refresh the network
        aggregates and compress chunks older than a week. Replaces any previous seeded history; live rows untouched."""
        if not self.timescale:
            return None
        t0 = time.perf_counter()
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM transfers WHERE seeded")
            await conn.execute("""
                INSERT INTO transfers (id, code, region_id, status, created_at, updated_at, doc, seeded)
                SELECT id, code, $3::text, 'closed', departed, arrived,
                       jsonb_build_object(
                         'id', id, 'code', code, 'region_id', $3::text, 'status', 'closed', 'seeded', true,
                         'origin_id', origin, 'destination_id', destination, 'mode', mode,
                         'departed_at', departed, 'handoff_at', handoff, 'arrived_at', arrived,
                         'acceptance', jsonb_build_object('by', 'Seeded history', 'at', handoff + accept_after),
                         'news2', jsonb_build_object('total', news2)),
                       true
                FROM (
                  SELECT gen_random_uuid() AS id, 'HX-' || to_char(n, 'FM00000') AS code,
                         ($4::text[])[1 + floor(random() * cardinality($4::text[]))::int] AS origin,
                         ($5::text[])[1 + floor(random() * cardinality($5::text[]))::int] AS destination,
                         ($6::text[])[1 + floor(random() * cardinality($6::text[]))::int] AS mode,
                         departed, departed + make_interval(mins => 4 + floor(random() * 20)::int) AS handoff,
                         departed + make_interval(mins => 45 + floor(random() * 150)::int) AS arrived,
                         -- most acceptances are quick, a few are slow: a long right tail like real phone chains
                         make_interval(secs => 60 + floor(random() * random() * 1500)::int) AS accept_after,
                         floor(random() * random() * 10)::int AS news2
                  FROM generate_series(1, $1::int * $2::int) AS n,
                       -- referencing n makes Postgres draw a fresh random() per row instead of once for all
                       LATERAL (SELECT now() - make_interval(secs => floor(random() * $1::int * 86400 + n * 0)::int) AS departed) d
                ) s""", days, per_day, region_id, origins, destinations, modes)
            await conn.execute("""
                INSERT INTO vitals_readings (transfer_id, recorded_at, id, source, heart_rate, resp_rate, hrv_rmssd, confidence)
                SELECT t.id, ts, gen_random_uuid(), 'simulated',
                       round(72 + t.news2 * 6 + (random() - 0.5) * 6), round(14 + t.news2 + (random() - 0.5) * 2),
                       round((42 - t.news2 * 2 + (random() - 0.5) * 4)::numeric, 1), 0.9
                FROM (SELECT id, (doc->>'departed_at')::timestamptz AS departed, (doc->>'arrived_at')::timestamptz AS arrived,
                             (doc->'news2'->>'total')::int AS news2
                      FROM transfers WHERE seeded) t,
                     LATERAL generate_series(t.departed, t.arrived, INTERVAL '10 seconds') AS ts""")
            await conn.execute("""
                INSERT INTO transfer_notes (transfer_id, at, id, author, kind, text)
                SELECT t.id, t.departed + (t.arrived - t.departed) * random(), gen_random_uuid(), x.author, x.kind, x.text
                FROM (SELECT id, (doc->>'departed_at')::timestamptz AS departed, (doc->>'arrived_at')::timestamptz AS arrived,
                             (doc->'news2'->>'total')::int AS news2
                      FROM transfers WHERE seeded) t
                CROSS JOIN LATERAL (  -- every random() mentions t so Postgres draws it per transfer, not once
                  SELECT 'crew' AS author, 'voice' AS kind, 'Seeded crew note' AS text
                  FROM generate_series(1, 1 + floor(random() * 3 + t.news2 * 0)::int)
                  UNION ALL SELECT 'system', 'alert', 'Seeded alert' FROM generate_series(1, floor(random() * (t.news2 / 2.0 + 0.6))::int)
                  UNION ALL SELECT 'hospital', 'question', 'Seeded question'
                  FROM generate_series(1, floor(random() * 2.4 + t.news2 * 0)::int)
                  UNION ALL SELECT 'system', 'event', 'Handoff sent'
                ) x""")
            for view in ("network_vitals_1h", "network_events_1d"):
                await self._refresh_aggregate(conn, view)
            compressed = 0
            for table in ("vitals_readings", "transfer_notes"):
                compressed += await conn.fetchval(
                    f"SELECT count(compress_chunk(c, if_not_compressed => true)) "
                    f"FROM show_chunks('{table}', older_than => INTERVAL '7 days') AS c")
            # reclaim the space of any previous seed and refresh planner statistics, so "on disk" is the honest figure
            await conn.execute("VACUUM ANALYZE vitals_readings, transfer_notes, transfers")
            counts = await conn.fetchrow("""
                SELECT (SELECT count(*) FROM transfers WHERE seeded) AS transfers,
                       (SELECT count(*) FROM vitals_readings v JOIN transfers t ON t.id = v.transfer_id WHERE t.seeded) AS readings,
                       (SELECT count(*) FROM transfer_notes n JOIN transfers t ON t.id = n.transfer_id WHERE t.seeded) AS notes""")
        return {**dict(counts), "compressed_chunks": compressed, "seconds": round(time.perf_counter() - t0, 1)}


def make_repo(database_url: str, use_memory: bool) -> Repo:
    if use_memory:
        return MemoryRepo()
    return PgRepo(database_url.replace("postgresql+asyncpg://", "postgresql://"))
