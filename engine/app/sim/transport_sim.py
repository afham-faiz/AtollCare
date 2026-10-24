# F-M4.4 Transport simulator. Every tick (2 s real) each dispatched / in-transit case is advanced along its frozen
# route schedule on the sim clock: position interpolated, transport_positions row written, departed /
# leg_completed / arrived events emitted, ETA updated. The schedule lives on the case (TransportState.route), so
# state is rebuilt from the DB after a restart.
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from app.core import refdata
from app.core.clock import fmt_local
from app.core.routing import MODE_LABELS
from app.models import Case, CaseStatus, EventType, GeoPoint, RouteOption, TrackPoint

log = logging.getLogger("atollcare.sim")


def position_at(route: RouteOption, t: datetime, origin: GeoPoint) -> tuple[GeoPoint, int | None, int, bool, float]:
    """Returns (position, current_leg_index, legs_completed, moving, speed_kmh)."""
    if not route.legs:
        return origin, None, 0, False, 0.0
    completed = sum(1 for leg in route.legs if leg.arrive_at <= t)
    for i, leg in enumerate(route.legs):
        if leg.depart_at <= t < leg.arrive_at:
            span = (leg.arrive_at - leg.depart_at).total_seconds() or 1
            f = (t - leg.depart_at).total_seconds() / span
            lat = leg.from_point.lat + (leg.to_point.lat - leg.from_point.lat) * f
            lng = leg.from_point.lng + (leg.to_point.lng - leg.from_point.lng) * f
            speed = leg.distance_km / (span / 3600)
            return GeoPoint(lat=lat, lng=lng), i, completed, True, speed
    if completed == 0:
        return route.legs[0].from_point, 0, 0, False, 0.0
    last = route.legs[completed - 1]
    nxt = completed if completed < len(route.legs) else completed - 1
    return last.to_point, nxt, completed, False, 0.0


class TransportSimulator:
    def __init__(self, cases, scenarios, tick_s: float = 2.0) -> None:
        self.cases = cases
        self.scenarios = scenarios
        self.tick_s = tick_s
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self.tick()
            except Exception:  # noqa: BLE001
                log.exception("simulator tick failed")
            await asyncio.sleep(self.tick_s)

    async def tick(self) -> None:
        await self.scenarios.tick()
        for case in await self.cases.repo.list_cases():
            if case.status in (CaseStatus.dispatched, CaseStatus.in_transit) and case.transport.route:
                await self.advance(case.id)

    async def advance(self, case_id) -> None:
        async with self.cases.locks[case_id]:
            case: Case | None = await self.cases.repo.get_case(case_id)
            if case is None or case.transport.route is None:
                return
            if case.status not in (CaseStatus.dispatched, CaseStatus.in_transit):
                return
            now = self.cases.now()
            route = case.transport.route
            t = case.transport
            pos, leg_idx, completed, moving, speed = position_at(route, now, case.origin_point)
            facs = refdata.facilities()
            # departed
            if route.legs and now >= route.legs[0].depart_at and t.status == "dispatched":
                first = route.legs[0]
                t.status = "in_transit"
                case.status = CaseStatus.in_transit
                await self.cases._event(
                    case, EventType.departed, "transport",
                    f"Departed {facs[first.from_id].label} by {MODE_LABELS[first.mode.value]}"
                    + (f" ({first.asset_id})" if first.asset_id else ""),
                    at=first.depart_at,
                )
            # legs completed since last tick
            interim = route.interim_stop_id
            for i in range(t.legs_completed, min(completed, len(route.legs))):
                leg = route.legs[i]
                if i == len(route.legs) - 1:
                    break
                note = ""
                if interim and leg.to_id == interim:
                    note = " — interim care / stabilisation"
                nxt = route.legs[i + 1]
                await self.cases._event(
                    case, EventType.leg_completed, "transport",
                    f"Reached {facs[leg.to_id].label}{note}. Next: {MODE_LABELS[nxt.mode.value]} departs "
                    f"{fmt_local(nxt.depart_at)}",
                    {"leg_index": i}, at=leg.arrive_at,
                )
            t.legs_completed = min(completed, len(route.legs))
            t.position = pos
            t.current_leg_index = leg_idx
            t.eta = route.arrive_at
            asset = route.legs[leg_idx].asset_id if leg_idx is not None and route.legs else None
            await self.cases.repo.add_position(
                case.id, TrackPoint(t=now, lat=pos.lat, lng=pos.lng, leg_index=leg_idx), asset,
                round(speed, 1) if moving else 0.0,
            )
            if not route.legs or now >= route.legs[-1].arrive_at:
                await self.cases._complete_arrival(case, route.legs[-1].arrive_at if route.legs else now, manual=False)
            await self.cases._save(case)
