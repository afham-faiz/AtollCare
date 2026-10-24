# F-M8.1 reset · F-M8.2 world controls · F-M3.8 capacity · F-M4.6 asset roster · F-M4.7 weather & daylight info.
# Every world change re-assesses open cases (debounced per case).
from __future__ import annotations

from app.core import refdata, routing, seed
from app.core.clock import daylight_bounds, fmt_local, is_daylight, tz
from app.models import (
    AssetPatch,
    CapacityPatch,
    ClockInfo,
    DemoState,
    DemoStatePatch,
    HospitalCapacity,
    TransportAsset,
)
from app.services.context import AppError, Services


class WorldService:
    def __init__(self, svc: Services, cases) -> None:
        self.svc = svc
        self.cases = cases
        self.repo = svc.repo

    async def load_state(self) -> None:
        state = await self.repo.get_demo_state()
        if state is None:
            state = DemoState(speed_multiplier=self.svc.settings.default_speed_multiplier)
            await self.repo.set_demo_state(state)
        self.svc.clock.load(state)
        if not await self.repo.list_assets():
            await self.reseed()

    async def reseed(self) -> None:
        for a in seed.seed_assets():
            await self.repo.upsert_asset(a)
        for c in seed.seed_capacity(self.svc.clock.now()):
            await self.repo.upsert_capacity(c)

    def state(self) -> DemoState:
        return self.svc.clock.state

    async def patch(self, p: DemoStatePatch, reassess: bool = True) -> DemoState:
        clock = self.svc.clock
        changes: list[str] = []
        if p.speed_multiplier is not None:
            clock.set_speed(p.speed_multiplier)
            changes.append(f"speed ×{p.speed_multiplier:g}")
        if p.clock_offset_min is not None:
            clock.set_offset(p.clock_offset_min)
            changes.append("clock offset")
        if p.set_time_of_day:
            try:
                clock.set_time_of_day(p.set_time_of_day)
            except ValueError as exc:
                raise AppError("invalid_time", "Use HH:MM", 422) from exc
            changes.append(f"time {p.set_time_of_day}")
        st = clock.state
        if p.weather is not None:
            w = st.weather.model_copy(update={k: v for k, v in p.weather.model_dump().items() if v is not None})
            st.weather = w
            changes.append("weather")
        if p.clear_night_override:
            st.night_override = None
        elif p.night_override is not None:
            st.night_override = p.night_override
            changes.append("night override")
        if p.helicopter_enabled is not None:
            st.helicopter_enabled = p.helicopter_enabled
            changes.append(f"helicopter {'on' if p.helicopter_enabled else 'off'}")
        await self.repo.set_demo_state(st)
        if reassess and changes:
            await self.cases.reassess_open("world changed: " + ", ".join(changes))
        return st

    def clock_info(self) -> ClockInfo:
        now = self.svc.clock.now()
        st = self.svc.clock.state
        local = now.astimezone(tz())
        sunrise, sunset, last = daylight_bounds(local.date())
        rctx = routing.RoutingContext(now=now, weather=st.weather, night_override=st.night_override,
                                      helicopter_enabled=st.helicopter_enabled)
        return ClockInfo(
            now=now,
            local_time=local.strftime("%H:%M"),
            is_daylight=is_daylight(now, st.night_override),
            sunrise=fmt_local(sunrise),
            sunset=fmt_local(sunset),
            seaplane_last_landing=fmt_local(last),
            disabled_modes=routing.disabled_modes(rctx),
        )

    async def reset(self) -> None:
        await self.repo.reset_cases()
        self.svc.scan_jobs.clear()
        self.svc.guidance_cache.clear()
        await self.reseed()

    # ---------------------------------------------------------------- capacity (F-M3.8)
    async def capacity(self) -> list[HospitalCapacity]:
        return await self.repo.list_capacity()

    async def patch_capacity(self, facility_id: str, p: CapacityPatch) -> HospitalCapacity:
        current = {c.facility_id: c for c in await self.repo.list_capacity()}.get(facility_id)
        if current is None:
            if refdata.facility(facility_id) is None:
                raise AppError("not_found", f"Unknown facility {facility_id}", 404)
            current = HospitalCapacity(facility_id=facility_id, updated_at=self.svc.clock.now())
        updated = current.model_copy(update={**p.model_dump(exclude_unset=True), "updated_at": self.svc.clock.now()})
        await self.repo.upsert_capacity(updated)
        fac = refdata.facility(facility_id)
        diff = [f"{k.replace('_', ' ')} {v}" for k, v in p.model_dump(exclude_unset=True).items()]
        await self.cases.reassess_open(f"{fac.label if fac else facility_id} capacity changed ({', '.join(diff)})")
        return updated

    # ---------------------------------------------------------------- assets (F-M4.6)
    async def assets(self) -> list[TransportAsset]:
        return await self.repo.list_assets()

    async def patch_asset(self, asset_id: str, p: AssetPatch) -> TransportAsset:
        asset = next((a for a in await self.repo.list_assets() if a.id == asset_id), None)
        if asset is None:
            raise AppError("not_found", f"Unknown asset {asset_id}", 404)
        asset.status = p.status
        await self.repo.upsert_asset(asset)
        await self.cases.reassess_open(f"{asset.id} is now {p.status}")
        return asset
