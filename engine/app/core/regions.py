# Region packs (engine/app/data/regions/*.json) and transport modes. A new region is one JSON file:
# hospitals + clinics + allowed modes + an example transfer. DEMO ASSUMPTION — coordinates approximate.
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Any

import yaml

from app.config import DATA_DIR
from app.models import Facility, GeoPoint, Region, RegionSummary, TransportMode, TransportModeInfo

REGIONS_DIR = DATA_DIR / "regions"


@lru_cache
def _raw_regions() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted(REGIONS_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out[data["id"]] = data
    return out


@lru_cache
def regions() -> dict[str, Region]:
    return {rid: Region.model_validate({k: v for k, v in d.items() if k != "cases"}) for rid, d in _raw_regions().items()}


def region(region_id: str) -> Region | None:
    return regions().get(region_id)


def region_summaries() -> list[RegionSummary]:
    return [RegionSummary(id=r.id, name=r.name, country=r.country, description=r.description) for r in regions().values()]


def cases() -> list[dict[str, Any]]:
    """Prepared demo cases from every region pack (each tagged with its region)."""
    return [{**c, "region_id": rid} for rid, d in _raw_regions().items() for c in d.get("cases", [])]


def case(case_id: str) -> dict[str, Any] | None:
    return next((c for c in cases() if c["id"] == case_id), None)


def facility(region_id: str, facility_id: str) -> Facility | None:
    r = region(region_id)
    if r is None:
        return None
    return next((f for f in r.facilities if f.id == facility_id), None)


@lru_cache
def modes() -> dict[TransportMode, TransportModeInfo]:
    raw = yaml.safe_load((DATA_DIR / "transport_modes.yaml").read_text(encoding="utf-8"))
    return {TransportMode(m["mode"]): TransportModeInfo(**m) for m in raw["modes"]}


def haversine_km(a: GeoPoint, b: GeoPoint) -> float:
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lng - a.lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def point(f: Facility) -> GeoPoint:
    return GeoPoint(lat=f.lat, lng=f.lng)


def journey(origin: Facility, destination: Facility, mode: TransportMode, departed_at: datetime) -> tuple[float, datetime]:
    """Returns (route distance km, ETA). Straight line × detour factor ÷ mode speed."""
    info = modes()[mode]
    km = haversine_km(point(origin), point(destination)) * info.detour
    return round(km, 1), departed_at + timedelta(hours=km / info.speed_kmh)


def interpolate(a: GeoPoint, b: GeoPoint, f: float) -> GeoPoint:
    f = max(0.0, min(1.0, f))
    return GeoPoint(lat=a.lat + (b.lat - a.lat) * f, lng=a.lng + (b.lng - a.lng) * f)
