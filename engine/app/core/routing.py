# F-M2.5 Routing — enumerate candidate routes (incl. infeasible, with reasons) on the sim clock.
# Graph = facility nodes from facilities.json. Distances: haversine × detour factor (sea/air/ground).
# Assets are dispatched in parallel at route start; a leg departs at max(patient ready, asset ready).
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from app.core import refdata
from app.core.clock import daylight_bounds, fmt_local, tz
from app.models import Facility, RouteLeg, RouteOption, TransportAsset, TransportMode, Weather

SEA_MODES = ("speedboat", "sea_ambulance")
MODE_LABELS = {
    "ground": "ground",
    "speedboat": "speedboat",
    "sea_ambulance": "sea ambulance",
    "seaplane": "seaplane",
    "fixed_wing": "fixed-wing",
    "helicopter": "helicopter",
}

Hop = tuple[str, str, str]  # (mode, from_id, to_id)


@dataclass
class RoutingContext:
    now: datetime
    weather: Weather
    night_override: bool | None = None
    helicopter_enabled: bool = False
    assets: list[TransportAsset] = field(default_factory=list)


@dataclass
class Schedule:
    legs: list[RouteLeg]
    end: datetime  # patient handed over at the last node (arrival + handover)
    reasons: list[str]
    used: dict[str, tuple[str, str]]  # mode → (asset_id, facility where it now is)

    @property
    def feasible(self) -> bool:
        return not self.reasons


# ---------------------------------------------------------------- geometry
def haversine_km(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(a_lat), math.radians(b_lat)
    dp, dl = p2 - p1, math.radians(b_lng - a_lng)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def fac_distance(a: Facility, b: Facility) -> float:
    return haversine_km(a.lat, a.lng, b.lat, b.lng)


def detour(mode: str) -> float:
    factors = refdata.transport_config()["detour_factor"]
    if mode in SEA_MODES:
        return factors["sea"]
    if mode == "ground":
        return factors["ground"]
    return factors["air"]


def ground_link(a: str, b: str) -> dict[str, Any] | None:
    for link in refdata.transport_config().get("ground_links", []):
        if {link["a"], link["b"]} == {a, b}:
            return link
    return None


# ---------------------------------------------------------------- hop templates
def connector(a: str, b: str, sea_mode: str = "speedboat") -> list[Hop]:
    if a == b:
        return []
    if ground_link(a, b):
        return [("ground", a, b)]
    return [(sea_mode, a, b)]


def airport_of(fac: Facility) -> str | None:
    if fac.has_airport:
        return fac.id
    return fac.nearest_airport_id


def hop_sequences(o: Facility, d: Facility) -> list[tuple[str, list[Hop]]]:
    """Route templates O → D. Returns (template_name, hops)."""
    if o.id == d.id:
        return [("local", [])]
    seqs: list[tuple[str, list[Hop]]] = []
    if ground_link(o.id, d.id):
        seqs.append(("ground", [("ground", o.id, d.id)]))
    # 1. sea direct
    for mode in SEA_MODES:
        seqs.append((mode, [(mode, o.id, d.id)]))
    # 2. seaplane (lagoon landing; IGMH via Hulhulé seaplane base + ground)
    if d.lagoon_access or d.seaplane_base_id:
        pre = connector(o.id, o.seaplane_base_id) if o.seaplane_base_id else []
        start = o.seaplane_base_id or o.id
        land = d.seaplane_base_id or d.id
        post = connector(land, d.id)
        if start != land:
            seqs.append(("seaplane", pre + [("seaplane", start, land)] + post))
    # 3. airport chain O ─sea→ A1 ─fixed_wing→ A2 ─(ground|sea)→ D (only when both ends have airports)
    a1, a2 = airport_of(o), airport_of(d)
    if a1 and a2 and a1 != a2:
        for sea_mode in SEA_MODES:
            first = connector(o.id, a1, sea_mode)
            if sea_mode != "speedboat" and not any(h[0] == sea_mode for h in first):
                continue  # variant only differs when there is a sea connector
            seqs.append((f"fixed_wing_via_{sea_mode}", first + [("fixed_wing", a1, a2)] + connector(a2, d.id)))
    # helicopter (point to point; disabled unless toggled)
    seqs.append(("helicopter", [("helicopter", o.id, d.id)]))
    return seqs


# ---------------------------------------------------------------- constraints
def mode_constraints(mode: str, ctx: RoutingContext) -> list[str]:
    spec = refdata.mode_specs()[mode]
    label = MODE_LABELS[mode]
    w = ctx.weather
    reasons: list[str] = []
    if mode == "helicopter" and not ctx.helicopter_enabled:
        reasons.append("helicopter: disabled (no medevac helicopter assumed — toggle in /demo)")
    if "disabled_sea_state_gte" in spec and w.sea_state >= spec["disabled_sea_state_gte"]:
        reasons.append(f"{label}: sea state {w.sea_state} ≥ {spec['disabled_sea_state_gte']}")
    if "max_wind_kt" in spec and w.wind_kt >= spec["max_wind_kt"]:
        reasons.append(f"{label}: wind {w.wind_kt:g} kt ≥ {spec['max_wind_kt']}")
    if "min_visibility_km" in spec and w.visibility_km < spec["min_visibility_km"]:
        reasons.append(f"{label}: visibility {w.visibility_km:g} km < {spec['min_visibility_km']}")
    return reasons


def disabled_modes(ctx: RoutingContext) -> dict[str, str]:
    """Modes currently disabled and why (weather, toggles, daylight) — for the F-M4.7 banner."""
    out: dict[str, str] = {}
    for mode in refdata.mode_specs():
        reasons = mode_constraints(mode, ctx)
        if mode == "seaplane":
            reason = daylight_reason(ctx.now, ctx.now, ctx)
            if reason:
                reasons.append(reason)
        if reasons:
            out[mode] = "; ".join(reasons)
    return out


def daylight_reason(depart: datetime, arrive: datetime, ctx: RoutingContext) -> str | None:
    if ctx.night_override is True:
        return "seaplane: night (demo override)"
    if ctx.night_override is False:
        return None
    local_dep = depart.astimezone(tz())
    sunrise, sunset, last = daylight_bounds(local_dep.date())
    if local_dep > sunset or local_dep < sunrise:
        return (
            f"seaplane: night — after sunset {fmt_local(sunset)} / before sunrise {fmt_local(sunrise)} "
            f"(would depart {fmt_local(depart)})"
        )
    if arrive.astimezone(tz()) > last:
        return (
            f"seaplane: would land {fmt_local(arrive)}, after last-landing cutoff {fmt_local(last)} "
            f"(sunset {fmt_local(sunset)} − 60 min return)"
        )
    return None


# ---------------------------------------------------------------- scheduling
def leg_speed(mode: str, a: str, b: str, ctx: RoutingContext) -> float:
    spec = refdata.mode_specs()[mode]
    speed = float(spec["speed_kmh"])
    if mode == "ground":
        link = ground_link(a, b)
        if link and link.get("effective_speed_kmh"):
            speed = float(link["effective_speed_kmh"])
    if "slow_sea_state" in spec and ctx.weather.sea_state == spec["slow_sea_state"]:
        speed *= spec.get("slow_factor", 1.0)
    return speed


def pick_asset(
    mode: str, at: Facility, ctx: RoutingContext, exclude: set[str]
) -> tuple[TransportAsset | None, float]:
    """Nearest available asset of a mode to facility `at`. Returns (asset, positioning_km)."""
    facs = refdata.facilities()
    best: tuple[TransportAsset | None, float] = (None, 0.0)
    best_d = math.inf
    for asset in ctx.assets:
        if asset.mode.value != mode or asset.status != "available" or asset.id in exclude:
            continue
        home = facs.get(asset.home_facility_id)
        if home is None:
            continue
        dist = fac_distance(home, at)
        if dist < best_d:
            best, best_d = (asset, dist), dist
    return best


def schedule(
    hops: list[Hop],
    route_start: datetime,
    patient_ready: datetime,
    ctx: RoutingContext,
    used: dict[str, tuple[str, str]] | None = None,
) -> Schedule:
    facs = refdata.facilities()
    used = dict(used or {})
    legs: list[RouteLeg] = []
    reasons: list[str] = []
    t = patient_ready
    for mode, a_id, b_id in hops:
        spec = refdata.mode_specs()[mode]
        a, b = facs[a_id], facs[b_id]
        reasons += [r for r in mode_constraints(mode, ctx) if r not in reasons]
        if mode == "ground" and not ground_link(a_id, b_id) and a_id != b_id:
            reasons.append(f"ground: {a.label} ↔ {b.label} not linked by road")
        if spec.get("airport_only") and not (a.has_airport and b.has_airport):
            reasons.append(f"{MODE_LABELS[mode]}: {a.label} ↔ {b.label} not both airports")
        speed = leg_speed(mode, a_id, b_id, ctx)
        dist = fac_distance(a, b) * detour(mode)
        dispatch_min = 0.0
        asset_id: str | None = None
        ready = route_start
        if spec.get("requires_asset", True):
            prior = used.get(mode)
            if prior and prior[1] == a_id:
                asset_id = prior[0]  # same asset continues; no new dispatch
                ready = t
            else:
                exclude = {v[0] for v in used.values()}
                asset, pos_km = pick_asset(mode, a, ctx, exclude)
                if asset is None:
                    reasons.append(f"no available {MODE_LABELS[mode]}")
                    pos_km = 0.0
                else:
                    asset_id = asset.id
                dispatch_min = float(spec["dispatch_min"])
                pos_min = pos_km * detour(mode) / speed * 60
                ready = route_start + timedelta(minutes=dispatch_min + pos_min)
                if mode == "seaplane" and pos_min > 0:
                    pos_reason = daylight_reason(route_start + timedelta(minutes=dispatch_min), ready, ctx)
                    if pos_reason and pos_reason not in reasons:
                        reasons.append(pos_reason)
        else:
            dispatch_min = float(spec["dispatch_min"])
            ready = route_start + timedelta(minutes=dispatch_min)
        depart = max(t, ready)
        travel = dist / speed * 60
        arrive = depart + timedelta(minutes=travel)
        if spec.get("daylight_only"):
            reason = daylight_reason(depart, arrive, ctx)
            if reason and reason not in reasons:
                reasons.append(reason)
        legs.append(
            RouteLeg(
                mode=TransportMode(mode),
                from_id=a_id,
                to_id=b_id,
                from_point=a.point,
                to_point=b.point,
                distance_km=round(dist, 1),
                dispatch_min=dispatch_min,
                travel_min=round(travel, 1),
                handover_min=float(spec["handover_min"]),
                depart_at=depart,
                arrive_at=arrive,
                asset_id=asset_id,
                wait_min=round((depart - t).total_seconds() / 60, 1),
            )
        )
        if asset_id:
            used[mode] = (asset_id, b_id)
        t = arrive + timedelta(minutes=float(spec["handover_min"]))
    return Schedule(legs=legs, end=t, reasons=reasons, used=used)


def best_schedule(
    o: Facility, d: Facility, route_start: datetime, patient_ready: datetime, ctx: RoutingContext,
    used: dict[str, tuple[str, str]] | None = None,
) -> tuple[str, Schedule] | None:
    """Fastest feasible sub-route O → D (falls back to fastest infeasible)."""
    options = [(name, schedule(h, route_start, patient_ready, ctx, used)) for name, h in hop_sequences(o, d)]
    if not options:
        return None
    feasible = [x for x in options if x[1].feasible]
    pool = feasible or options
    return min(pool, key=lambda x: x[1].end)


# ---------------------------------------------------------------- route options
def _route_id(dest: str, legs: list[RouteLeg], interim: str | None) -> str:
    parts = [f"{leg.mode.value}>{leg.to_id}" for leg in legs]
    if interim:
        parts.insert(0, f"via:{interim}")
    return dest + "|" + ("|".join(parts) if parts else "local")


def _label(legs: list[RouteLeg], interim: Facility | None, interim_label: str | None, origin: Facility) -> str:
    facs = refdata.facilities()
    if not legs:
        return f"Treat at {origin.label} — no transfer"
    chunks: list[str] = []
    if interim is not None and interim.id == origin.id:
        chunks.append(f"{interim_label or 'Stabilise'} at {origin.label}")
    for leg in legs:
        chunks.append(f"{MODE_LABELS[leg.mode.value].capitalize()} to {facs[leg.to_id].label}")
        if interim is not None and leg.to_id == interim.id and interim.id != origin.id:
            chunks.append(interim_label or "Stabilise")
    return " → ".join(chunks)


def build_option(
    origin: Facility,
    dest: Facility,
    legs: list[RouteLeg],
    end: datetime,
    reasons: list[str],
    ctx: RoutingContext,
    kind: str,
    interim: Facility | None = None,
    interim_label: str | None = None,
    interim_arrive: datetime | None = None,
) -> RouteOption:
    total = (end - ctx.now).total_seconds() / 60
    medic = any(refdata.mode_specs()[leg.mode.value].get("medic_onboard") for leg in legs)
    opt = RouteOption(
        id=_route_id(dest.id, legs, interim.id if interim else None),
        destination_id=dest.id,
        legs=legs,
        total_min=round(total, 1),
        arrive_at=end,
        feasible=not reasons,
        infeasible_reasons=reasons,
        interim_stop_id=interim.id if interim else None,
        kind=kind,  # type: ignore[arg-type]
        label=_label(legs, interim, interim_label, origin),
        medic_onboard=medic,
    )
    if interim_arrive is not None:
        opt.interim_arrive_min = round((interim_arrive - ctx.now).total_seconds() / 60, 1)
    return opt


def enumerate_routes(
    origin: Facility,
    destinations: list[Facility],
    ctx: RoutingContext,
    interim_spec: dict[str, Any] | None = None,
    interim_candidates: list[Facility] | None = None,
) -> list[RouteOption]:
    routes: dict[str, RouteOption] = {}
    start = ctx.now
    for dest in destinations:
        for name, hops in hop_sequences(origin, dest):
            sch = schedule(hops, start, start, ctx)
            kind = "local" if name == "local" else "direct"
            opt = build_option(origin, dest, sch.legs, sch.end, sch.reasons, ctx, kind)
            routes.setdefault(opt.id, opt)
        if not interim_spec or not interim_candidates:
            continue
        stabilise = float(interim_spec.get("stabilise_min", 30))
        nearest = sorted(interim_candidates, key=lambda h: fac_distance(origin, h))[:3]
        for h in nearest:
            if h.id == dest.id:
                continue
            first = best_schedule(origin, h, start, start, ctx)
            if first is None:
                continue
            _, s1 = first
            interim_arrive = s1.legs[-1].arrive_at if s1.legs else start
            second = best_schedule(h, dest, start, s1.end + timedelta(minutes=stabilise), ctx, s1.used)
            if second is None:
                continue
            _, s2 = second
            reasons = list(dict.fromkeys(s1.reasons + s2.reasons))
            opt = build_option(
                origin, dest, s1.legs + s2.legs, s2.end, reasons, ctx, "interim",
                interim=h, interim_label=interim_spec.get("label"), interim_arrive=interim_arrive,
            )
            routes.setdefault(opt.id, opt)
    return list(routes.values())
