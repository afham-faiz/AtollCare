# Network insights for operations leads: how fast handoffs are accepted, where transfers go, how many alerts and
# questions a day — answered from Tiger Data continuous aggregates, with the storage and query cost shown alongside.
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from app.core import regions
from app.models import (
    BenchmarkResponse,
    InsightsDay,
    InsightsDestination,
    InsightsKpis,
    InsightsResponse,
    SeedHistoryResponse,
    StorageTable,
    TimedQuery,
)
from app.services.context import AppError, Services

UNAVAILABLE = "Network insights need Tiger Data. Set DATABASE_URL to a Tiger Cloud (or TimescaleDB) service."


def _facility_name(facility_id: str) -> str:
    for r in regions.regions().values():
        f = next((f for f in r.facilities if f.id == facility_id), None)
        if f:
            return f.short_name
    return facility_id


def _num(v: Any) -> float | None:
    return round(float(v), 1) if v is not None else None


class InsightsService:
    def __init__(self, svc: Services) -> None:
        self.svc = svc

    async def insights(self, days: int) -> InsightsResponse:
        database, version = self.svc.infra.database, self.svc.infra.database_version
        data = await self.svc.repo.insights(days)
        if data is None:
            return InsightsResponse(available=False, reason=UNAVAILABLE, database=database, database_version=version,
                                    days=days)
        k = data["kpis"]
        daily: dict[datetime, InsightsDay] = defaultdict(lambda: InsightsDay(day=datetime.min))
        for r in data["per_day"]:
            daily[r["day"]].transfers = r["n"]
        for r in data["events"]:
            setattr(daily[r["day"]], "alerts" if r["kind"] == "alert" else "questions", r["n"])
        for r in data["readings"]:
            daily[r["day"]].readings = r["n"]
        for day, item in daily.items():
            item.day = day
        return InsightsResponse(
            available=True, database=database, database_version=version, days=days,
            seeded_transfers=k["seeded"], live_transfers=k["live"],
            kpis=InsightsKpis(
                transfers=k["transfers"], handed_off=k["handed_off"], accepted=k["accepted"],
                median_min_to_accept=_num(k["median_accept"]), p90_min_to_accept=_num(k["p90_accept"]),
                median_journey_min=_num(k["median_journey"]), high_risk=k["high_risk"],
            ),
            daily=sorted(daily.values(), key=lambda d: d.day),
            destinations=[
                InsightsDestination(destination_id=r["destination_id"], name=_facility_name(r["destination_id"]),
                                    transfers=r["n"], median_min_to_accept=_num(r["median_accept"]))
                for r in data["destinations"]
            ],
            storage=[StorageTable(**s) for s in data["storage"]],
            aggregates=data["aggregates"],
            queries=[TimedQuery(**q) for q in data["queries"]],
        )

    async def benchmark(self, days: int) -> BenchmarkResponse:
        b = await self.svc.repo.benchmark(days)
        if b is None:
            raise AppError("needs_tiger", UNAVAILABLE, 409)
        return BenchmarkResponse(
            question=f"Vitals readings per hour across the network, last {days} days", days=days,
            aggregate_source="network_vitals_1h (continuous aggregate)", aggregate_ms=b["aggregate_ms"],
            raw_ms=b["raw_ms"], rows_scanned=b["rows_scanned"],
            speedup=round(b["raw_ms"] / b["aggregate_ms"], 1) if b["aggregate_ms"] > 0 else 0.0,
        )

    async def seed(self, days: int, per_day: int) -> SeedHistoryResponse:
        region = regions.region(self.svc.clock.state.region_id)
        if region is None:
            raise AppError("unknown_region", "Active region is not installed", 500)
        hospitals = [f.id for f in region.facilities if f.kind != "clinic"] or [f.id for f in region.facilities]
        clinics = [f.id for f in region.facilities if f.id not in hospitals] or hospitals
        modes = [m.value if hasattr(m, "value") else str(m) for m in region.modes] or ["boat"]
        out = await self.svc.repo.seed_history(days, per_day, region.id, clinics, hospitals, modes)
        if out is None:
            raise AppError("needs_tiger", UNAVAILABLE, 409)
        return SeedHistoryResponse(**out)
