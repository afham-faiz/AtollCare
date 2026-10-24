# Network insights over the transfer_log hypertable: seed demo history, query the daily continuous aggregate.
from __future__ import annotations

import logging
import time
from datetime import timedelta

from app.core import insights as insights_mod
from app.core import regions
from app.models import InsightsResponse, SeedResponse
from app.services.context import AppError, Services

log = logging.getLogger("atollcare.insights")
MAX_DAYS = 365


class InsightsService:
    def __init__(self, svc: Services) -> None:
        self.svc = svc

    def _region(self, region_id: str | None):  # noqa: ANN202
        rid = region_id or self.svc.clock.state.region_id
        region = regions.region(rid)
        if region is None:
            raise AppError("unknown_region", f"No region pack named {rid}", 422)
        return region

    async def get(self, days: int, region_id: str | None) -> InsightsResponse:
        if not 1 <= days <= MAX_DAYS:
            raise AppError("bad_days", f"days must be 1–{MAX_DAYS}", 422)
        region = self._region(region_id)
        since = self.svc.clock.now() - timedelta(days=days)
        return await self.svc.repo.insights(region.id, days, since, region.timezone)

    async def seed(self, days: int, region_id: str | None) -> SeedResponse:
        """Replaces this region's seeded history (live rows are kept)."""
        if not 1 <= days <= MAX_DAYS:
            raise AppError("bad_days", f"days must be 1–{MAX_DAYS}", 422)
        region = self._region(region_id)
        t0 = time.perf_counter()
        await self.svc.repo.clear_seeded(region.id)
        rows = insights_mod.seed_rows(region, days, self.svc.clock.now())
        await self.svc.repo.log_transfers(rows)
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        log.info("seeded %d history rows for %s (%d days) in %.0f ms", len(rows), region.id, days, elapsed)
        return SeedResponse(inserted=len(rows), days=days, region_id=region.id, elapsed_ms=elapsed)

    async def clear(self, region_id: str | None) -> int:
        return await self.svc.repo.clear_seeded(self._region(region_id).id)
