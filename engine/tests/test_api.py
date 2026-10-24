# §13 API smoke tests for every endpoint in mock mode (TestClient).
import time

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.hub import get_hub


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        c.post("/api/demo/reset")
        c.patch("/api/demo/state", json={"set_time_of_day": "11:00", "speed_multiplier": 1,
                                          "weather": {"sea_state": 2, "wind_kt": 10, "visibility_km": 10}})
        yield c


def ok(resp, status=200):
    assert resp.status_code == status, resp.text
    return resp.json()


def test_meta_and_health(client):
    meta = ok(client.get("/api/meta"))
    assert any(f["id"] == "igmh" for f in meta["facilities"])
    assert meta["adapters"] == {"presage": "mock", "gemini": "mock", "elevenlabs": "mock", "storage": "mock"}
    assert len(meta["scenarios"]) == 5
    assert meta["clock"]["local_time"] == "11:00"
    health = ok(client.get("/api/health"))
    assert health["ok"] and health["db"].startswith("memory")


def test_full_case_lifecycle(client):
    case = ok(client.post("/api/cases", json={"origin_facility_id": "dhangethi_hc", "patient": {"age": 34, "sex": "M"}}))
    cid = case["id"]
    assert case["status"] == "draft" and case["short_code"].startswith("AC-")
    case = ok(client.patch(f"/api/cases/{cid}", json={"patient": {"age": 35, "sex": "M", "allergies": ["penicillin"]}}))
    assert case["patient"]["age"] == 35
    case = ok(client.post(f"/api/cases/{cid}/intake",
                          json={"raw_text": "Fell from a coconut tree 20 minutes ago, open fracture, bleeding heavily"}))
    assert case["intake"]["suspected_conditions"][0]["condition_id"] == "major_trauma"
    case = ok(client.post(f"/api/cases/{cid}/vitals", json={
        "heart_rate": 135, "resp_rate": 26, "spo2": 90, "on_oxygen": False, "systolic_bp": 88,
        "temperature_c": 39.5, "consciousness": "V"}))
    assert case["news2"]["total"] == 17 and case["news2"]["band"] == "high"
    case = ok(client.post(f"/api/cases/{cid}/submit"))
    assert case["status"] == "assessed"
    rec = case["recommendation"]
    assert rec["severity"] == "critical" and rec["destination_id"] == "igmh"
    assert case["headline"]["text"].startswith("Symptom → definitive care")
    ok(client.post(f"/api/cases/{cid}/assess"))
    routes = ok(client.get(f"/api/cases/{cid}/routes"))
    assert any(not r["feasible"] for r in routes) and any(r["feasible"] for r in routes)
    trend = ok(client.get(f"/api/cases/{cid}/vitals/trend?window_min=60"))
    assert trend["buckets"] and trend["buckets"][0]["news2"] == 17
    sbar = ok(client.get(f"/api/cases/{cid}/sbar"))
    assert sbar["generated_by"] == "template" and "penicillin" in sbar["background"]
    guidance = ok(client.get(f"/api/cases/{cid}/guidance?role=reporter"))
    assert guidance["steps"] and guidance["disclaimer"]

    case = ok(client.post(f"/api/cases/{cid}/refer", json={"note": "Please accept"}, headers={"X-Role": "clinician"}))
    assert case["status"] == "referred" and case["referral"]["sbar"]
    inbox = ok(client.get("/api/cases?destination_id=igmh"))
    assert [i["id"] for i in inbox] == [cid]

    case = ok(client.post(f"/api/cases/{cid}/referral/respond",
                          json={"response": "needs_info", "responder_name": "Dr A", "info_requests": ["Blood loss?"]}))
    assert case["status"] == "needs_info"
    case = ok(client.post(f"/api/cases/{cid}/referral/info", json={"answers": {"Blood loss?": "About 1 litre"}}))
    assert case["status"] == "referred" and case["referral"]["info_answers"][0]["answer"] == "About 1 litre"

    case = ok(client.post(f"/api/cases/{cid}/referral/respond", json={"response": "accepted", "responder_name": "Dr A"}))
    assert case["status"] == "accepted"
    route_id = case["recommendation"]["chosen_route_id"]
    case = ok(client.post(f"/api/cases/{cid}/dispatch", json={"route_id": route_id}))
    assert case["status"] == "dispatched"
    assets = ok(client.get("/api/transport/assets"))
    assert any(a["status"] == "busy" for a in assets)
    track = ok(client.get(f"/api/cases/{cid}/track"))
    assert track["positions"] and track["transport"]["status"] == "dispatched"

    client.patch("/api/demo/state", json={"speed_multiplier": 3600})
    time.sleep(3)  # ≈ 3 sim hours
    hub = get_hub()
    client.portal.call(hub.sim.tick)  # type: ignore[attr-defined]
    case = ok(client.get(f"/api/cases/{cid}"))
    assert case["status"] == "arrived", [e["summary"] for e in case["timeline"]]
    types = [e["type"] for e in case["timeline"]]
    assert "departed" in types and "arrived" in types

    case = ok(client.post(f"/api/cases/{cid}/notes", json={"text": "Handover done", "actor_role": "specialist"}))
    case = ok(client.post(f"/api/cases/{cid}/close", json={"outcome_note": "Surgery done"}))
    assert case["status"] == "closed"
    assert case["headline"]["saved_vs_baseline_min"] > 0


def test_decline_replans_and_resends(client):
    case = ok(client.post("/api/demo/scenario/stroke_capacity_flip"))
    cid = case["id"]
    assert case["recommendation"]["destination_id"] == "igmh"
    ok(client.post(f"/api/cases/{cid}/refer", json={}))
    case = ok(client.post(f"/api/cases/{cid}/referral/respond",
                          json={"response": "declined", "responder_name": "Dr B", "note": "No stroke bed"}))
    assert case["status"] == "referred"
    assert case["referral"]["destination_id"] != "igmh"
    assert "igmh" in case["referral"]["declined_destination_ids"]
    assert any(e["type"] == "replanned" for e in case["timeline"])
    # decline requires a reason
    r = client.post(f"/api/cases/{cid}/referral/respond", json={"response": "declined", "responder_name": "Dr C"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "missing_reason"


def test_capacity_flip_replans(client):
    case = ok(client.post("/api/demo/scenario/stroke_capacity_flip"))
    cid = case["id"]
    assert case["recommendation"]["destination_id"] == "igmh"
    caps = ok(client.get("/api/hospitals/capacity"))
    assert any(c["facility_id"] == "igmh" for c in caps)
    ok(client.patch("/api/hospitals/igmh/capacity", json={"ct_available": False}))
    time.sleep(2.2)  # per-case re-assessment is debounced to once per 2 s
    case = ok(client.get(f"/api/cases/{cid}"))
    assert case["recommendation"]["destination_id"] == "kulhudhuffushi_rh"
    assert any(e["type"] == "replanned" for e in case["timeline"])


def test_asset_offline_and_demo_controls(client):
    ok(client.patch("/api/transport/assets/sp_hulhule_1", json={"status": "offline"}))
    assets = {a["id"]: a for a in ok(client.get("/api/transport/assets"))}
    assert assets["sp_hulhule_1"]["status"] == "offline"
    st = ok(client.patch("/api/demo/state", json={"set_time_of_day": "21:00", "weather": {"sea_state": 6},
                                                  "helicopter_enabled": True}))
    assert st["weather"]["sea_state"] == 6 and st["helicopter_enabled"]
    meta = ok(client.get("/api/meta"))
    assert "speedboat" in meta["clock"]["disabled_modes"] and "seaplane" in meta["clock"]["disabled_modes"]
    assert ok(client.get("/api/demo/state"))["helicopter_enabled"]


def test_all_scenarios_load(client):
    for sid in ["laamu_stemi_night", "daytime_trauma", "stroke_capacity_flip", "pph_weather", "sepsis_local"]:
        case = ok(client.post(f"/api/demo/scenario/{sid}"))
        assert case["status"] == "assessed", sid
        assert case["recommendation"], sid
    hero = ok(client.post("/api/demo/scenario/laamu_stemi_night"))
    chosen = next(r for r in hero["recommendation"]["alternatives"] if r["id"] == hero["recommendation"]["chosen_route_id"])
    assert chosen["interim_stop_id"] == "gan_l_rh"


def test_voice_and_media(client):
    t = ok(client.post("/api/voice/transcribe", files={"audio": ("v.webm", b"fake-audio", "audio/webm")}))
    assert "chest pain" in t["text"] and t["source"] == "mock"
    s = ok(client.post("/api/voice/speak", json={"text": "Hello", "voice": "guide"}))
    assert s["audio_url"] is None and s["source"] == "browser"
    r = client.get("/api/media/nope.webm")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


def test_scan_job_mock(client):
    case = ok(client.post("/api/demo/scenario/laamu_stemi_night"))
    cid = case["id"]
    job = ok(client.post(f"/api/cases/{cid}/vitals/scan", files={"video": ("scan.webm", b"\x1a\x45\xdf\xa3", "video/webm")}))
    status = {}
    for _ in range(20):
        status = ok(client.get(f"/api/vitals/scan/{job['job_id']}"))
        if status["status"] in ("done", "failed"):
            break
        time.sleep(0.5)
    assert status["status"] == "done", status
    assert 100 <= status["reading"]["heart_rate"] <= 125
    media = status["reading"]["media_url"]
    assert client.get(media).status_code == 200
    ok(client.get(f"/api/cases/{cid}/status-sentence"))
    ok(client.get(f"/api/cases/{cid}/crew-brief"))


def test_errors_shape(client):
    r = client.get("/api/cases/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/cases", json={"origin_facility_id": "nowhere"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_origin"
    r = client.post("/api/cases", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
