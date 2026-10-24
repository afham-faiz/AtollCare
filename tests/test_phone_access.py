import time

import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.services import jobs

TUNNEL = {"Cf-Connecting-Ip": "203.0.113.9", "X-Forwarded-Proto": "https"}   # what cloudflared adds


@pytest.fixture
def client():
    return TestClient(app, follow_redirects=False)


def test_the_laptop_itself_needs_no_key(client):
    assert client.get("/api/health").status_code == 200


def test_tunnel_traffic_without_the_key_is_refused(client):
    assert client.get("/api/health", headers=TUNNEL).status_code == 401
    assert client.get("/phone", headers=TUNNEL).status_code == 401


def test_a_wrong_key_is_refused(client):
    assert client.get("/phone?key=nope", headers=TUNNEL).status_code == 401


def test_the_link_with_the_key_sets_a_cookie_and_then_everything_works():
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)   # a Secure cookie is only sent over https
    first = client.get("/phone?key=test-token-123", headers=TUNNEL)
    assert first.status_code == 303 and first.headers["location"] == "/phone"
    cookie = first.headers["set-cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "test-token-123" in cookie
    assert client.get("/phone", headers=TUNNEL).status_code == 200      # the client kept the cookie
    assert client.get("/api/health", headers=TUNNEL).status_code == 200


def test_the_key_in_a_post_url_does_not_log_you_in(client):
    assert client.post("/api/scan-id?key=test-token-123", headers=TUNNEL).status_code == 401


def test_with_no_token_configured_all_tunnel_traffic_is_refused(client, monkeypatch):
    monkeypatch.setattr(config, "ACCESS_TOKEN", "")
    resp = client.get("/phone?key=", headers=TUNNEL)
    assert resp.status_code == 401 and b"ACCESS_TOKEN" in resp.content
    assert client.get("/api/health").status_code == 200                # the laptop is unaffected


def test_the_microphone_socket_is_gated_too(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/transcribe", headers=TUNNEL):
            pass


def test_a_job_reports_done_with_its_result():
    job = jobs.start(lambda: {"x": 1})
    for _ in range(50):
        if jobs.get(job)["state"] != "running":
            break
        time.sleep(0.05)
    assert jobs.get(job) == {"state": "done", "result": {"x": 1}}


def test_a_failing_job_reports_the_reason():
    def boom():
        raise ValueError("bad clip")
    job = jobs.start(boom)
    for _ in range(50):
        if jobs.get(job)["state"] != "running":
            break
        time.sleep(0.05)
    assert jobs.get(job) == {"state": "error", "detail": "ValueError: bad clip"}


def test_an_unknown_job_is_a_404(client):
    assert client.get("/api/jobs/missing").status_code == 404


def test_latest_capture_pairs_the_video_check_with_its_vitals_and_account(monkeypatch):
    from src.app import latest_capture
    import src.app as appmod
    report = {"plan": {}, "findings": []}
    monkeypatch.setattr(appmod, "read_visual_cues", lambda n=20: [{"video": "b.webm", "logged_at": "2026-01-01T00:00:00+00:00",
                                                                   "transcript": "he fell", "report": report}])
    monkeypatch.setattr(appmod, "read_history", lambda n=20: [{"video": "other.webm", "result": {"heart_rate_bpm": 1}},
                                                              {"video": "b.webm", "result": {"heart_rate_bpm": 88, "diagnostics": {"x": 1}}}])
    monkeypatch.setattr(appmod, "read_id_scans", lambda n=20: [])
    got = latest_capture()
    assert got["id"] is None
    assert got["video"]["account"] == "he fell" and got["video"]["vitals"] == {"heart_rate_bpm": 88, "diagnostics": {}}


def test_latest_capture_with_nothing_saved(monkeypatch):
    import src.app as appmod
    for name in ("read_visual_cues", "read_history", "read_id_scans"):
        monkeypatch.setattr(appmod, name, lambda n=20: [])
    assert appmod.latest_capture() == {"video": None, "id": None}
