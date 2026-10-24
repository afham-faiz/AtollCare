# Persistence. PgRepo = TimescaleDB / Tiger Cloud (hypertables + continuous aggregate). MemoryRepo = same interface
# in-process, used by tests and when DATABASE_URL is empty (no-docker dev). The engine owns the database.
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
        # rows only — never drop tables
        async with self.pool.acquire() as conn:
            for table in ("vitals_readings", "transfer_notes", "transfers"):
                await conn.execute(f"DELETE FROM {table}")


def make_repo(database_url: str, use_memory: bool) -> Repo:
    if use_memory:
        return MemoryRepo()
    return PgRepo(database_url.replace("postgresql+asyncpg://", "postgresql://"))
