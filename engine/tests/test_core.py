# Core logic: region packs, journeys, Presage validity flags, alerts, note extraction, briefing template.
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from app.core import alerts, briefing, regions
from app.core.vitals import presage_flag, simulated_values, update_latest
from app.models import (
    AlertLevel,
    DeteriorationForecast,
    News2Result,
    SimProfile,
    TransportMode,
    VitalsReading,
    VitalsSource,
)

NOW = datetime(2026, 10, 24, 12, tzinfo=UTC)


def test_region_packs_load_and_examples_are_valid():
    packs = regions.regions()
    assert {"maldives", "scotland"} <= set(packs)
    for r in packs.values():
        assert any(f.kind == "hospital" for f in r.facilities)
    for c in regions.cases():
        r = packs[c["region_id"]]
        assert regions.facility(r.id, c["origin_id"]) and regions.facility(r.id, c["destination_id"]), c["id"]
        assert TransportMode(c["mode"]) in r.modes


def test_journey_eta_scales_with_mode():
    o = regions.facility("maldives", "dhiffushi_hc")
    d = regions.facility("maldives", "igmh")
    km_boat, eta_boat = regions.journey(o, d, TransportMode.boat, NOW)
    _km_heli, eta_heli = regions.journey(o, d, TransportMode.helicopter, NOW)
    assert 40 < km_boat < 55  # ~37 km straight line × 1.25 sea detour
    assert eta_heli < eta_boat
    assert timedelta(minutes=60) < eta_boat - NOW < timedelta(minutes=90)


def test_presage_flag_outside_validated_range():
    assert presage_flag("heart_rate", 118, VitalsSource.presage)
    assert presage_flag("heart_rate", 96, VitalsSource.presage) is None
    assert presage_flag("heart_rate", 118, VitalsSource.manual) is None


def test_latest_ignores_low_quality_and_older_readings():
    tid = uuid4()
    good = VitalsReading(id=uuid4(), transfer_id=tid, recorded_at=NOW, source="presage", heart_rate=90, confidence=0.9)
    bad = VitalsReading(id=uuid4(), transfer_id=tid, recorded_at=NOW + timedelta(seconds=5), source="presage",
                        heart_rate=150, confidence=0.3, low_quality=True)
    older = VitalsReading(id=uuid4(), transfer_id=tid, recorded_at=NOW - timedelta(minutes=1), source="manual", heart_rate=70)
    latest = update_latest(update_latest(update_latest({}, good), bad), older)
    assert latest["heart_rate"].value == 90


def test_simulated_values_are_plausible_and_drift():
    p = SimProfile(heart_rate=100, heart_rate_per_hour=24)
    early = simulated_values(p, NOW, NOW, 1)
    late = simulated_values(p, NOW, NOW + timedelta(hours=1), 1)
    assert 90 <= early["heart_rate"] <= 110
    assert late["heart_rate"] > early["heart_rate"] + 10


def test_alerts_raise_once_and_keep_since():
    n2 = News2Result(total=7, components={}, any_single_3=False, band="high", complete=True, missing=[])
    first = alerts.evaluate(n2, {}, None, [], NOW)
    assert [a.code for a in first] == ["news2_high"] and first[0].level == AlertLevel.critical
    again = alerts.evaluate(n2, {}, None, first, NOW + timedelta(minutes=5))
    assert again[0].since == NOW
    assert alerts.new_alerts(first, again) == []


def test_alert_on_rising_heart_rate_forecast():
    fc = DeteriorationForecast(slope_per_hour=2, projected_news2_at_arrival=6, minutes_to_news2_7=20, trend="worsening",
                               confidence="low", points_used=8, hr_slope_per_hour=24)
    codes = {a.code for a in alerts.evaluate(None, {}, fc, [], NOW)}
    assert {"hr_rising", "news2_rising"} <= codes


def test_rule_extraction_of_interventions_and_observations():
    e = briefing.extract("Gave aspirin 300 mg at departure. Pain 8 out of 10, sweating, ST elevation inferior leads")
    assert any("aspirin 300 mg" in i.lower() for i in e.interventions)
    assert any(o.lower().startswith("pain 8") for o in e.observations)
    assert any("st elevation" in o.lower() for o in e.observations)
    assert briefing.extract("Not on anticoagulants").interventions == []


def test_rule_extraction_splits_each_treatment():
    e = briefing.extract("Gave aspirin 300 mg and GTN spray. Oxygen 4 litres. Pain 8 out of 10.")
    assert e.interventions == ["Aspirin 300 mg", "GTN spray", "Oxygen 4 litres"]
    assert briefing.extract("Gave adrenaline 0.5 mg IM").interventions == ["Adrenaline 0.5 mg IM"]
    assert briefing.extract("Started IV fluids 500 ml, applied pelvic binder").interventions == ["IV fluids 500 ml", "Pelvic binder"]
    # patient's own medication and negatives are not treatments given
    assert briefing.extract("Takes aspirin daily. No blood thinners").interventions == []


def test_rule_extraction_reads_speech_to_text():
    # as the browser / Scribe transcribed a real crew note: spelled-out units, dose before the drug
    e = briefing.extract("I can't speak administer 300 milligrams of aspirin to the patient")
    assert e.interventions == ["Aspirin 300 mg"]
    assert briefing.extract("Giving morphine 5 milligrams IV").interventions == ["Morphine 5 mg IV"]


def test_suspected_condition_keywords():
    assert "STEMI" in briefing.suspected_condition("crushing chest pain going to the left arm")
    assert "stroke" in briefing.suspected_condition("slurred speech and facial droop").lower()
    assert briefing.suspected_condition("feels unwell") is None


def test_stroke_with_arm_weakness_is_not_stemi():
    s = briefing.suspected_condition("Sudden weakness of the left arm and slurred speech")
    assert s and "stroke" in s.lower()
