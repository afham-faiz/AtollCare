# Where this engine runs. On a Vultr instance the link-local metadata service answers within milliseconds; anywhere
# else the request fails fast and we report "Local". Read once at startup — the UI shows facts, never assumptions.
from __future__ import annotations

import logging

import httpx

log = logging.getLogger("atollcare.infra")
VULTR_METADATA = "http://169.254.169.254/v1.json"


async def detect_host(declared: str = "", declared_region: str = "", timeout_s: float = 0.4) -> tuple[str, str | None, str | None]:
    """Returns (host, region code, plan) — ("Vultr", "lhr", "vc2-2c-4gb") from the metadata service; else what the
    operator declared in HOST_LABEL / HOST_REGION; else ("Local", None, None)."""
    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.get(VULTR_METADATA)
        resp.raise_for_status()
        data = resp.json()
    except Exception:  # noqa: BLE001 — not on Vultr (or metadata blocked): that's the normal local case
        return (declared, declared_region or None, None) if declared else ("Local", None, None)
    region = (data.get("region") or {}).get("regioncode")
    plan = data.get("plan") or (data.get("instance") or {}).get("plan")
    log.info("running on Vultr: region=%s plan=%s", region, plan)
    return "Vultr", region.lower() if isinstance(region, str) else None, plan if isinstance(plan, str) else None
