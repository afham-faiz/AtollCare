# F-M2.1 / F-M2.5 Decision engine orchestrator: NEWS2 → severity → condition & window → candidate routes →
# score & choose → forecast → baseline. Deterministic; the Gemini explanation is layered on by the service.
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime

from app.config import ENGINE_VERSION
from app.core import baseline as baseline_mod
from app.core import conditions as cond
from app.core import forecast as forecast_mod
from app.core import news2 as news2_mod
from app.core import refdata, routing
from app.models import (
    SEVERITY_ORDER,
    Case,
    HospitalCapacity,
    Recommendation,
    RouteOption,
    TransportAsset,
    TrendBucket,
    Weather,
)

BREACH_WEIGHT = 3.0
MEDIC_BONUS = 10.0
FORECAST_MEDIC_BONUS = 20.0
EXTRA_HANDOVER_PENALTY = 15.0
INFEASIBLE_PENALTY = 1000.0


@dataclass
class AssessContext:
    now: datetime
    weather: Weather = field(default_factory=Weather)
    night_override: bool | None = None
    helicopter_enabled: bool = False
    assets: list[TransportAsset] = field(default_factory=list)
    capacity: dict[str, HospitalCapacity] = field(default_factory=dict)
    trend: list[TrendBucket] = field(default_factory=list)
    declined: set[str] = field(default_factory=set)
    pin_destination: str | None = None  # referred/overridden destination, kept while it remains a valid candidate


@dataclass
class AssessResult:
    recommendation: Recommendation
    routes: list[RouteOption]
    news2: object


def fmt_min(minutes: float | None) -> str:
    if minutes is None:
        return "—"
    m = int(round(minutes))
    sign = "-" if m < 0 else ""
    m = abs(m)
    if m < 60:
        return f"{sign}{m} min"
    return f"{sign}{m // 60} h {m % 60:02d} min"


def _short(fid: str) -> str:
    fac = refdata.facility(fid)
    return fac.label if fac else fid


def score_route(
    r: RouteOption,
    elapsed: float,
    window: float | None,
    severity: str,
    cctx: cond.ConditionContext | None = None,
    medic_extra: float = 0.0,
) -> None:
    """score = total + 3×breach − medic bonus + 15/extra handover + 1000 if infeasible (§8.5). For interim plans the
    3× breach applies to the interim window (that is where time-critical care happens); the definitive-care delay
    counts 1×. Preferred capabilities (conditions.yaml) give a bonus only when the route meets the window."""
    breakdown: dict[str, float] = {"total_min": r.total_min}
    definitive_breach = elapsed + r.total_min - window if window is not None and r.within_window is False else 0.0
    interim = (cctx.interim if cctx else None) or {}
    if r.kind == "interim" and r.interim_arrive_min is not None and interim:
        interim_breach = elapsed + r.interim_arrive_min - interim.get("window_min", 0)
        if interim_breach > 0:
            breakdown["interim_breach_penalty"] = round(BREACH_WEIGHT * interim_breach, 1)
        if definitive_breach > 0:
            breakdown["definitive_delay_penalty"] = round(definitive_breach, 1)
    elif definitive_breach > 0:
        breakdown["breach_penalty"] = round(BREACH_WEIGHT * definitive_breach, 1)
    preferred = (cctx.spec.get("preferred_capabilities") if cctx else None) or {}
    dest = refdata.facility(r.destination_id)
    if preferred and dest and r.within_window is not False:
        bonus = sum(v for k, v in preferred.items() if k in dest.capabilities)
        if bonus:
            breakdown["preferred_capability_bonus"] = -float(bonus)
    if r.medic_onboard and SEVERITY_ORDER.index(severity) >= SEVERITY_ORDER.index("high"):
        breakdown["medic_bonus"] = -MEDIC_BONUS
    if r.medic_onboard and medic_extra:
        breakdown["forecast_medic_bonus"] = -medic_extra
    extra = max(0, len(r.legs) - 2)
    if extra:
        breakdown["extra_handovers"] = EXTRA_HANDOVER_PENALTY * extra
    if not r.feasible:
        breakdown["infeasible"] = INFEASIBLE_PENALTY
    r.score_breakdown = breakdown
    r.score = round(sum(breakdown.values()), 1)


def choose(routes: list[RouteOption]) -> tuple[RouteOption, str]:
    """Returns (chosen, tier). Tiers: in_window → interim → best_feasible → none_feasible."""
    in_window = [r for r in routes if r.kind != "interim" and r.feasible and r.within_window is not False]
    if in_window:
        return min(in_window, key=lambda r: r.score), "in_window"
    interim_ok = [r for r in routes if r.kind == "interim" and r.feasible and r.interim_within_window]
    if interim_ok:
        return min(interim_ok, key=lambda r: r.score), "interim"
    feasible = [r for r in routes if r.feasible]
    if feasible:
        return min(feasible, key=lambda r: r.score), "best_feasible"
    return min(routes, key=lambda r: r.score), "none_feasible"


def top_alternatives(routes: list[RouteOption], chosen: RouteOption, n: int = 3) -> list[RouteOption]:
    ranked = sorted(routes, key=lambda r: r.score)
    # prefer distinct destinations/kinds so the comparison is informative
    picked: list[RouteOption] = [chosen]
    for r in ranked:
        if len(picked) >= n:
            break
        if r.id == chosen.id:
            continue
        picked.append(r)
    return sorted(picked, key=lambda r: (r.id != chosen.id, r.score))


def breach_text(
    tier: str, chosen: RouteOption, routes: list[RouteOption], cctx: cond.ConditionContext
) -> str | None:
    window = cctx.window_min
    label = cctx.spec.get("window_label", "definitive care")
    if tier == "none_feasible":
        reasons = list(dict.fromkeys(x for r in routes for x in r.infeasible_reasons))
        return "No feasible transport under current conditions. Blocking: " + "; ".join(reasons[:5]) + "."
    if tier == "in_window" or window is None:
        return None
    direct = [r for r in routes if r.kind == "direct" and r.feasible]
    best_direct = min(direct, key=lambda r: r.total_min) if direct else None
    best_txt = f" (fastest: {fmt_min(best_direct.total_min)} to {_short(best_direct.destination_id)})" if best_direct else ""
    if tier == "interim" and chosen.interim_stop_id:
        interim = cctx.interim or {}
        eta = "now" if not chosen.interim_arrive_min else f"ETA {fmt_min(chosen.interim_arrive_min)}"
        stop_idx = next((i for i, leg in enumerate(chosen.legs) if leg.to_id == chosen.interim_stop_id), -1)
        modes = [routing.MODE_LABELS[leg.mode.value] for leg in chosen.legs[stop_idx + 1:] if leg.mode.value != "ground"]
        how = f" by {' + '.join(dict.fromkeys(modes))}" if modes else ""
        return (
            f"No route reaches {label.replace('to ', '')} within {int(window)} min{best_txt}. "
            f"Recommended: {interim.get('label', 'Stabilise')} at {_short(chosen.interim_stop_id)} ({eta}), "
            f"then{how} to {_short(chosen.destination_id)}."
        )
    over = cctx.time_since_start_min + chosen.total_min - window
    return (
        f"No route reaches {label.replace('to ', '')} within the {int(window)}-min window — best ETA "
        f"{fmt_min(chosen.total_min)} ({fmt_min(over)} over). Escalate and start local measures."
    )


def template_explanation(chosen: RouteOption, alternatives: list[RouteOption], routes: list[RouteOption]) -> str:
    parts = [f"{chosen.label} reaches {_short(chosen.destination_id)} in {fmt_min(chosen.total_min)}."]
    others = [r for r in alternatives if r.id != chosen.id and r.feasible]
    if others:
        alt = others[0]
        diff = alt.total_min - chosen.total_min
        if diff > 0:
            alt_label = alt.label[:1].lower() + alt.label[1:]
            parts.append(f"That is {fmt_min(diff)} sooner than {alt_label} ({fmt_min(alt.total_min)}).")
        elif chosen.within_window and alt.within_window and chosen.score_breakdown.get("preferred_capability_bonus"):
            parts.append(
                f"{alt.label} is {fmt_min(-diff)} faster, but {_short(chosen.destination_id)} has the preferred "
                f"specialist service and still meets the window."
            )
        elif chosen.kind == "interim":
            parts.append(
                f"{alt.label} arrives {fmt_min(-diff)} earlier but misses the treatment window, so interim treatment "
                f"comes first."
            )
    rejected = next((r for r in routes if not r.feasible and any("seaplane" in x for x in r.infeasible_reasons)), None)
    if rejected:
        reason = next(x for x in rejected.infeasible_reasons if "seaplane" in x)
        parts.append(f"Seaplane rejected — {reason.split(': ', 1)[-1]}.")
    return " ".join(parts[:3])


def input_hash(chosen: RouteOption, alternatives: list[RouteOption], breach: str | None) -> str:
    payload = {
        "chosen": chosen.id,
        "total": round(chosen.total_min / 5),
        "alts": [(a.id, round(a.total_min / 5), a.feasible) for a in alternatives],
        "breach": breach,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def actions_for(condition_id: str, role: str = "clinician") -> list[str]:
    lib = refdata.first_aid()
    steps = (lib["conditions"].get(condition_id) or lib["conditions"]["other"]).get(role, [])
    return [s["text"] for s in steps]


def assess(case: Case, ctx: AssessContext) -> AssessResult:
    origin = refdata.facility(case.origin_facility_id)
    if origin is None:
        raise ValueError(f"unknown origin facility {case.origin_facility_id}")
    news2 = news2_mod.compute(case.vitals, ctx.now)
    cctx = cond.condition_context(case.intake, case.created_at, ctx.now)
    severity = cond.severity_for(news2, case.intake, cctx)
    caps = cond.required_capabilities(cctx, severity)
    candidates, rejected = cond.candidate_destinations(caps, ctx.capacity, ctx.declined)
    warnings: list[str] = []
    if rejected:
        warnings.append("Excluded: " + "; ".join(rejected))
    if not candidates:
        fallback = [f for f in refdata.facilities().values() if f.type == "tertiary_hospital" and f.id not in ctx.declined]
        fallback = fallback or [refdata.facilities()["igmh"]]
        warnings.append(f"No facility currently meets {', '.join(caps)}; falling back to {fallback[0].label}.")
        candidates = fallback
    pinned = [c for c in candidates if c.id == ctx.pin_destination]
    if pinned:
        candidates = pinned
    rctx = routing.RoutingContext(
        now=ctx.now,
        weather=ctx.weather,
        night_override=ctx.night_override,
        helicopter_enabled=ctx.helicopter_enabled,
        assets=ctx.assets,
    )
    interim_spec = cctx.interim
    interim_cands = cond.interim_facilities(interim_spec, origin, ctx.capacity, ctx.declined) if interim_spec else None
    routes = routing.enumerate_routes(origin, candidates, rctx, interim_spec, interim_cands)

    elapsed = cctx.time_since_start_min
    window = cctx.window_min
    for r in routes:
        if window is not None:
            r.within_window = elapsed + r.total_min <= window
            r.window_margin_min = round(window - (elapsed + r.total_min), 1)
        if interim_spec and r.kind == "interim" and r.interim_arrive_min is not None:
            r.interim_within_window = elapsed + r.interim_arrive_min <= interim_spec.get("window_min", window or 0)
        score_route(r, elapsed, window, severity.value, cctx)

    chosen, tier = choose(routes)
    fc = forecast_mod.forecast(ctx.trend, ctx.now, chosen.arrive_at)
    if fc and fc.projected_news2_at_arrival is not None and fc.projected_news2_at_arrival >= 7 and not chosen.medic_onboard:
        warnings.append(
            f"Trend suggests NEWS2 ≈ {fc.projected_news2_at_arrival:g} by arrival ({fc.points_used} points) and the "
            f"chosen route has no medic onboard — prefer sea ambulance / medevac."
        )
        for r in routes:
            score_route(r, elapsed, window, severity.value, cctx, FORECAST_MEDIC_BONUS)
        chosen, tier = choose(routes)

    alternatives = top_alternatives(routes, chosen)
    breach = breach_text(tier, chosen, routes, cctx)
    meta = case.meta
    base = baseline_mod.compare(chosen, meta.submitted_at, meta.accepted_at)
    rec = Recommendation(
        severity=severity,
        primary_condition_id=cctx.condition_id,
        window_min=window,
        time_since_onset_min=round(elapsed, 1),
        destination_id=chosen.destination_id,
        required_capabilities=caps,
        chosen_route_id=chosen.id,
        alternatives=alternatives,
        actions_now=actions_for(cctx.condition_id, "clinician"),
        explanation=template_explanation(chosen, alternatives, routes),
        breach_warning=breach,
        forecast=fc,
        baseline=base,
        generated_at=ctx.now,
        engine_version=ENGINE_VERSION,
        warnings=warnings,
        explanation_source="template",
        input_hash=input_hash(chosen, alternatives, breach),
        onset_confidence=cctx.onset_confidence,  # type: ignore[arg-type]
        interim_window_min=(interim_spec or {}).get("window_min"),
        condition_probabilities=case.intake.suspected_conditions if case.intake else [],
        all_routes_count=len(routes),
    )
    return AssessResult(recommendation=rec, routes=sorted(routes, key=lambda r: r.score), news2=news2)
