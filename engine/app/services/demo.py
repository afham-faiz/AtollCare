# Demo controls: sim speed, active region pack, reset. Persisted in demo_state so a restart keeps the stage setup.
from __future__ import annotations

from app.core import regions
from app.models import DemoState, DemoStatePatch, MetaResponse
from app.services.context import AppError, Services
from app.services.transfers import PREPARE_OPTIONS


class DemoService:
    def __init__(self, svc: Services) -> None:
        self.svc = svc

    async def load_state(self) -> None:
        state = await self.svc.repo.get_demo_state()
        if state is None:
            state = DemoState(speed_multiplier=self.svc.settings.default_speed_multiplier,
                              region_id=self.svc.settings.default_region)
            await self.svc.repo.set_demo_state(state)
        if regions.region(state.region_id) is None:
            state.region_id = next(iter(regions.regions()))
        self.svc.clock.load(state)

    async def patch(self, p: DemoStatePatch) -> DemoState:
        if p.region_id is not None:
            if regions.region(p.region_id) is None:
                raise AppError("unknown_region", f"No region pack named {p.region_id}", 422)
            self.svc.clock.state.region_id = p.region_id
        if p.speed_multiplier is not None:
            self.svc.clock.set_speed(p.speed_multiplier)
        await self.svc.repo.set_demo_state(self.svc.clock.state)
        return self.svc.clock.state

    async def reset(self) -> None:
        await self.svc.repo.reset()
        self.svc.caches.clear()
        self.svc.clock.reset()
        await self.svc.repo.set_demo_state(self.svc.clock.state)

    def meta(self) -> MetaResponse:
        state = self.svc.clock.state
        return MetaResponse(
            region=regions.region(state.region_id),  # type: ignore[arg-type]
            regions=list(regions.regions().values()),
            modes=list(regions.modes().values()),
            adapters=self.svc.adapter_status(),
            bridge=self.svc.bridge_status(),
            demo_state=state,
            now=self.svc.clock.now(),
            prepare_options=PREPARE_OPTIONS,
        )
