# API smoke tests for every endpoint in mock mode (TestClient, in-memory store).
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.hub import get_hub


@pytest.fixture()
def client():
    with TestClient(create_app()) as c:
        c.post("/api/demo/reset")
        c.patch("/api/demo/state", json={"region_id": "maldives", "speed_multiplier": 1})
        yield c


def ok(resp, status=200):
    assert resp.status_code == status, resp.text
    return resp.json()


def create(c, **kw):
    body = {"patient": {"age": 58, "sex": "M"}, "complaint": "Crushing chest pain, sweating",
            "origin_id": "dhiffushi_hc", "destination_id": "igmh", "mode": "boat"} | kw
    return ok(c.post("/api/transfers", json=body))


def test_meta_health_and_regions(client):
    meta = ok(client.get("/api/meta"))
    assert meta["region"]["id"] == "maldives"
    assert {r["id"] for r in meta["regions"]} >= {"maldives", "scotland"}
    assert meta["adapters"]["presage"] == "simulated"
    assert meta["prepare_options"]
    ok(client.patch("/api/demo/state", json={"region_id": "scotland"}))
    assert ok(client.get("/api/meta"))["region"]["timezone"] == "Europe/London"
    r = client.patch("/api/demo/state", json={"region_id": "atlantis"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_region"
    assert ok(client.get("/api/health"))["db"].startswith("memory")


def test_create_validates_region_facilities(client):
    r = client.post("/api/transfers", json={"complaint": "x", "origin_id": "castlebay", "destination_id": "igmh",
                                             "mode": "boat"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "unknown_facility"
    r = client.post("/api/transfers", json={"complaint": "x", "origin_id": "igmh", "destination_id": "igmh",
                                             "mode": "boat"})
    assert r.json()["error"]["code"] == "same_place"
    r = client.post("/api/transfers", json={"complaint": "x", "origin_id": "dhiffushi_hc", "destination_id": "igmh",
                                             "mode": "road"})
    assert r.json()["error"]["code"] == "mode_unavailable"


def test_full_transfer_lifecycle(client):
    t = create(client)
    tid = t["id"]
    assert t["status"] == "pending" and t["code"].startswith("AC-")
    assert t["briefing"]["generated_by"] == "template"
    assert t["notes"][0]["kind"] == "event"

    # contactless (bridge) + manual vitals → NEWS2, latest values with Presage flag
    ack = ok(client.post(f"/api/transfers/{tid}/vitals", json={"source": "presage", "heart_rate": 118, "resp_rate": 24,
                                                                "confidence": 0.8, "hint": "Hold still"}))
    assert ack["monitoring"]["source"] == "presage" and ack["monitoring"]["hint"] == "Hold still"
    assert not ack["news2"]["complete"]
    ack = ok(client.post(f"/api/transfers/{tid}/vitals", json={"spo2": 90, "on_oxygen": False, "systolic_bp": 88,
                                                                "temperature_c": 39.5, "consciousness": "V"}))
    assert ack["news2"]["total"] >= 7
    assert any(a["level"] == "critical" for a in ack["alerts"])
    t = ok(client.get(f"/api/transfers/{tid}"))
    assert t["latest"]["heart_rate"]["flag"]  # 118 > Presage validated 110
    assert any(n["kind"] == "alert" for n in t["notes"])

    # crew note → interventions + briefing refresh
    t = ok(client.post(f"/api/transfers/{tid}/notes", json={"text": "Gave aspirin 300 mg. Pain 8 out of 10.",
                                                             "kind": "voice"}))
    assert t["interventions"][0]["text"].lower().startswith("gave aspirin 300 mg")
    assert "already given: aspirin" in t["briefing"]["recommendation"].lower()

    # hospital asks → crew answers (reply_to) → list shows no unanswered questions
    t = ok(client.post(f"/api/transfers/{tid}/messages", json={"text": "Any blood thinners?", "sender": "Dr A"}))
    q = next(n for n in t["notes"] if n["kind"] == "question")
    assert ok(client.get("/api/transfers"))[0]["unanswered_questions"] == 1
    t = ok(client.post(f"/api/transfers/{tid}/notes", json={"text": "No blood thinners", "reply_to": q["id"]}))
    assert t["notes"][-1]["kind"] == "answer"
    assert ok(client.get("/api/transfers"))[0]["unanswered_questions"] == 0

    # accept → message spoken in the vehicle
    t = ok(client.post(f"/api/transfers/{tid}/accept", json={"by": "Dr Shareef", "prepare": ["Cath lab"]}))
    assert t["status"] == "accepted" and t["acceptance"]["prepare"] == ["Cath lab"]
    assert "cath lab" in t["notes"][-1]["text"].lower()

    trend = ok(client.get(f"/api/transfers/{tid}/vitals/trend?window_min=60"))
    assert trend["buckets"] and trend["source"] == "memory"

    t = ok(client.post(f"/api/transfers/{tid}/monitoring", json={"source": "simulated"}))
    assert t["monitoring"]["source"] == "simulated"
    t = ok(client.post(f"/api/transfers/{tid}/arrive"))
    assert t["status"] == "arrived" and t["progress"] == 1
    t = ok(client.post(f"/api/transfers/{tid}/close"))
    assert t["status"] == "closed"
    r = client.post(f"/api/transfers/{tid}/vitals", json={"heart_rate": 80})
    assert r.status_code == 409


def test_simulator_tick_moves_vehicle_and_emits_simulated_vitals(client):
    t = create(client)
    client.patch("/api/demo/state", json={"speed_multiplier": 600})
    import time

    time.sleep(1.2)  # ≈ 12 sim minutes
    client.portal.call(get_hub().transfers.tick)  # type: ignore[attr-defined]
    t = ok(client.get(f"/api/transfers/{t['id']}"))
    assert 0 < t["progress"] < 1
    assert t["position"] != t["origin_point"]
    assert any(v["source"] == "simulated" for v in t["vitals"])


def test_auto_arrival_at_eta(client):
    t = create(client, mode="helicopter")
    client.patch("/api/demo/state", json={"speed_multiplier": 600})
    import time

    time.sleep(2)  # ≈ 20 sim minutes > ~13 min helicopter flight
    client.portal.call(get_hub().transfers.tick)  # type: ignore[attr-defined]
    t = ok(client.get(f"/api/transfers/{t['id']}"))
    assert t["status"] == "arrived"


def test_example_transfer_for_each_region(client):
    for rid in ("maldives", "scotland"):
        ok(client.patch("/api/demo/state", json={"region_id": rid}))
        t = ok(client.post("/api/demo/example"))
        assert t["region_id"] == rid
        assert len(t["vitals"]) >= 10 and t["news2"]["complete"]
        assert t["interventions"] or rid == "scotland"
        trend = ok(client.get(f"/api/transfers/{t['id']}/vitals/trend"))
        assert len(trend["buckets"]) >= 5 and trend["forecast"]


def test_voice_and_speak_mock(client):
    t = create(client)
    r = client.post(f"/api/transfers/{t['id']}/notes/voice", files={"audio": ("n.webm", b"abc", "audio/webm")})
    assert r.status_code == 501 and r.json()["error"]["code"] == "stt_unavailable"
    s = ok(client.post("/api/voice/speak", json={"text": "Hospital asks: any allergies?"}))
    assert s["audio_url"] is None and s["source"] == "browser"


def test_bridge_heartbeat_switches_presage_status(client):
    ok(client.post("/api/presage/heartbeat", json={"sdk": "ready", "version": "3.4.0", "clients": 1}))
    meta = ok(client.get("/api/meta"))
    assert meta["adapters"]["presage"] == "live" and meta["bridge"]["connected"]
    ok(client.post("/api/presage/heartbeat", json={"sdk": "no_api_key"}))
    assert ok(client.get("/api/meta"))["adapters"]["presage"] == "simulated"


def test_errors_shape(client):
    r = client.get("/api/transfers/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    r = client.post("/api/transfers", json={})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    t = create(client)
    r = client.post(f"/api/transfers/{t['id']}/vitals", json={"source": "manual"})
    assert r.status_code == 422 and r.json()["error"]["code"] == "empty_reading"
