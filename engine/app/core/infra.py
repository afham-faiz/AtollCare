# Where the engine runs and what it stores data in, for the presenter panel and /api/health. Detected at startup:
# the Vultr instance metadata service (169.254.169.254) and the DMI vendor string; the database from the server itself.
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import Settings
from app.models import InfraStatus

log = logging.getLogger("atollcare.infra")
DMI_VENDOR = Path("/sys/class/dmi/id/sys_vendor")
TIGER_HOST_MARKERS = ("tsdb.cloud.timescale.com", "timescale.com", "tigerdata", "tsdb.cloud")


def region_code(meta: dict[str, Any]) -> str | None:
    """Vultr's v1.json carries the region as {"region": {"regioncode": "LHR"}}; tolerate a flat string too."""
    region = meta.get("region")
    if isinstance(region, dict):
        code = region.get("regioncode") or region.get("region_code") or region.get("id")
        return str(code).upper() if code else None
    if isinstance(region, str) and region:
        return region.upper()
    return None


def host_text(provider: str | None, region: str | None) -> str:
    if not provider:
        return "This computer"
    return f"{provider} · {region.upper()}" if region else provider


async def detect_host(settings: Settings) -> tuple[str | None, str | None, str]:
    """Returns (provider label, region code, source)."""
    if settings.host_label:
        return settings.host_label, settings.host_region.upper() or None, "env"
    if not settings.metadata_url:
        return None, None, "none"
    try:
        async with httpx.AsyncClient(timeout=settings.metadata_timeout_s) as client:
            res = await client.get(settings.metadata_url)
        if res.status_code == 200:
            meta = res.json()
            if isinstance(meta, dict) and (meta.get("instanceid") or meta.get("instance-v2-id") or meta.get("region")):
                return "Vultr", region_code(meta), "metadata"
    except Exception as exc:  # noqa: BLE001 — not on Vultr, or no link-local route
        log.debug("instance metadata unavailable: %s", exc)
    try:
        if DMI_VENDOR.exists() and "vultr" in DMI_VENDOR.read_text(encoding="utf-8").lower():
            return "Vultr", None, "metadata"
    except OSError:
        pass
    return None, None, "none"


def database_text(kind: str, dsn: str, timescale_version: str | None, server_version: str | None) -> tuple[str, str]:
    """Returns (label, kind) for the presenter panel."""
    if kind == "memory":
        return "In-memory (demo)", "memory"
    host = (urlparse(dsn).hostname or "").lower()
    if timescale_version:
        if any(m in host for m in TIGER_HOST_MARKERS):
            return f"Tiger Cloud · TimescaleDB {timescale_version}", "tiger_cloud"
        return f"TimescaleDB {timescale_version}", "timescaledb"
    major = (server_version or "").split(".")[0]
    return (f"PostgreSQL {major}" if major else "PostgreSQL"), "postgres"


async def detect(settings: Settings, repo: Any) -> InfraStatus:
    provider, region, source = await detect_host(settings)
    ts_version, server_version = await repo.versions()
    db_label, db_kind = database_text(repo.kind, getattr(repo, "dsn", ""), ts_version, server_version)
    return InfraStatus(
        database=db_label, database_kind=db_kind,  # type: ignore[arg-type]
        host=host_text(provider, region),
        host_provider=provider.lower() if provider else None, host_region=region, host_source=source,  # type: ignore[arg-type]
    )
