# §8.9 Engine tests — routing constraints, scenario decisions, fallback intake.
from datetime import timedelta

from app.core import decision, fallback_intake, refdata, routing, seed
from app.models import Weather
from tests.helpers import at_local, case_from_scenario, ctx_for, trend_from_vitals


def _rctx(hhmm: str, **kw) -> routing.RoutingContext:
    return routing.RoutingContext(now=at_local(hhmm), assets=seed.seed_assets(), **kw)


def _routes(o: str, d: str, rctx: routing.RoutingContext):
    facs = refdata.facilities()
    return routing.enumerate_routes(facs[o], [facs[d]], rctx)


def test_night_disables_seaplane():
    routes = _routes("isdhoo_hc", "igmh", _rctx("21:00", weather=Weather()))
    seaplane = [r for r in routes if any(leg.mode.value == "seaplane" for leg in r.legs)]
    assert seaplane, "seaplane template should be enumerated"
    assert all(not r.feasible for r in seaplane)
    assert any("night" in reason for r in seaplane for reason in r.infeasible_reasons)


def test_day_allows_seaplane():
    routes = _routes("dhangethi_hc", "igmh", _rctx("11:00", weather=Weather()))
    seaplane = [r for r in routes if any(leg.mode.value == "seaplane" for leg in r.legs)]
    assert any(r.feasible for r in seaplane)


def test_seaplane_last_landing_cutoff():
    routes = _routes("vaadhoo_hc", "thinadhoo_rh", _rctx("17:30", weather=Weather()))
    seaplane = [r for r in routes if any(leg.mode.value == "seaplane" for leg in r.legs)]
    assert seaplane and all(not r.feasible for r in seaplane)


def test_sea_state_6_disables_both_sea_modes():
    routes = _routes("isdhoo_hc", "gan_l_rh", _rctx("11:00", weather=Weather(sea_state=6)))
    for mode in ("speedboat", "sea_ambulance"):
        rs = [r for r in routes if [leg.mode.value for leg in r.legs] == [mode]]
        assert rs and not rs[0].feasible
        assert any("sea state 6" in x for x in rs[0].infeasible_reasons)


def test_sea_state_5_disables_speedboat_only():
    routes = _routes("isdhoo_hc", "gan_l_rh", _rctx("11:00", weather=Weather(sea_state=5)))
    by_mode = {tuple(leg.mode.value for leg in r.legs): r for r in routes}
    assert not by_mode[("speedboat",)].feasible
    assert by_mode[("sea_ambulance",)].feasible


def test_airport_chain_only_when_both_ends_have_airports():
    facs = refdata.facilities()
    # Muli has no airport and no nearest_airport_id → no fixed-wing chain
    seqs = routing.hop_sequences(facs["isdhoo_hc"], facs["muli_ah"])
    assert not any(any(h[0] == "fixed_wing" for h in hops) for _, hops in seqs)
    seqs = routing.hop_sequences(facs["isdhoo_hc"], facs["igmh"])
    chain = [hops for _, hops in seqs if any(h[0] == "fixed_wing" for h in hops)]
    assert chain and chain[0][1] == ("fixed_wing", "kadhdhoo", "hulhule")


def test_no_available_asset_makes_mode_infeasible():
    rctx = _rctx("11:00", weather=Weather())
    rctx.assets = [a for a in rctx.assets if a.mode.value != "seaplane"]
    routes = _routes("dhangethi_hc", "igmh", rctx)
    sp = [r for r in routes if any(leg.mode.value == "seaplane" for leg in r.legs)]
    assert sp and all("no available seaplane" in r.infeasible_reasons for r in sp)


def test_hero_laamu_stemi_night_chooses_interim_fibrinolysis_then_fixed_wing():
    case, now = case_from_scenario("laamu_stemi_night")
    res = decision.assess(case, ctx_for(now, trend=trend_from_vitals(case.vitals)))
    rec = res.recommendation
    chosen = next(r for r in rec.alternatives if r.id == rec.chosen_route_id)
    assert rec.primary_condition_id == "stemi"
    assert rec.severity.value == "critical"
    assert chosen.kind == "interim"
    assert chosen.interim_stop_id == "gan_l_rh"
    assert rec.destination_id == "igmh"
    modes = [leg.mode.value for leg in chosen.legs]
    assert "fixed_wing" in modes and "seaplane" not in modes
    fw = next(leg for leg in chosen.legs if leg.mode.value == "fixed_wing")
    assert (fw.from_id, fw.to_id) == ("kadhdhoo", "hulhule")
    assert rec.breach_warning and "Gan" in rec.breach_warning
    assert rec.baseline.saved_vs_baseline_min > 0


def test_daytime_trauma_chooses_seaplane_to_igmh():
    case, now = case_from_scenario("daytime_trauma")
    rec = decision.assess(case, ctx_for(now)).recommendation
    chosen = next(r for r in rec.alternatives if r.id == rec.chosen_route_id)
    assert rec.primary_condition_id == "major_trauma"
    assert rec.destination_id == "igmh"
    assert chosen.legs[0].mode.value == "seaplane"
    assert any(any(leg.mode.value == "sea_ambulance" for leg in r.legs) for r in decision.assess(
        case, ctx_for(now)).routes)


def test_stroke_capacity_flip_replans_to_kulhudhuffushi():
    case, now = case_from_scenario("stroke_capacity_flip")
    ctx = ctx_for(now)
    assert decision.assess(case, ctx).recommendation.destination_id == "igmh"
    ctx.capacity["igmh"].ct_available = False
    assert decision.assess(case, ctx).recommendation.destination_id == "kulhudhuffushi_rh"


def test_sepsis_local_treats_at_origin_first():
    case, now = case_from_scenario("sepsis_local")
    rec = decision.assess(case, ctx_for(now)).recommendation
    chosen = next(r for r in rec.alternatives if r.id == rec.chosen_route_id)
    assert rec.primary_condition_id == "sepsis"
    assert chosen.interim_stop_id == "dhiffushi_hc"
    assert "icu" in rec.required_capabilities


def test_pph_sea_state_6_reports_no_feasible_transport():
    case, now = case_from_scenario("pph_weather")
    rec = decision.assess(case, ctx_for(now, weather=Weather(sea_state=6))).recommendation
    assert rec.breach_warning and "No feasible transport" in rec.breach_warning
    rec2 = decision.assess(case, ctx_for(now, weather=Weather(sea_state=6), helicopter_enabled=True)).recommendation
    chosen = next(r for r in rec2.alternatives if r.id == rec2.chosen_route_id)
    assert chosen.feasible and chosen.legs[0].mode.value == "helicopter"


def test_decline_excludes_destination():
    case, now = case_from_scenario("stroke_capacity_flip")
    rec = decision.assess(case, ctx_for(now, declined={"igmh"})).recommendation
    assert rec.destination_id != "igmh"


def test_fallback_intake_detects_stemi():
    intake = fallback_intake.extract("crushing chest pain left arm sweating", at_local("12:00"))
    assert intake.suspected_conditions[0].condition_id == "stemi"
    assert intake.suspected_conditions[0].probability >= 0.4
    assert intake.red_flags
    assert intake.extracted_by == "fallback_rules"


def test_fallback_intake_parses_relative_onset():
    now = at_local("12:00")
    intake = fallback_intake.extract("weakness and slurred speech, started about 50 minutes ago", now)
    assert intake.onset_time == now - timedelta(minutes=50)
    assert intake.onset_confidence == "approx"
