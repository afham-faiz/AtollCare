import json

from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.services import transcript_log

CHUNK = bytes(3200)  # 100 ms of silence at 16 kHz, 16-bit mono


def test_mock_transcription_flow_and_log(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")  # never hit the real service in tests
    log = tmp_path / "transcripts.json"
    monkeypatch.setattr(transcript_log, "LOG_PATH", log)

    events = []
    with TestClient(app).websocket_connect("/ws/transcribe") as ws:
        events.append(ws.receive_json())
        for _ in range(25):  # 2.5 s of audio
            ws.send_bytes(CHUNK)
        ws.send_text("end")
        while events[-1]["type"] not in ("done", "error"):
            events.append(ws.receive_json())

    assert events[0]["type"] == "ready" and events[0]["mode"] == "mock"
    done = events[-1]
    assert done["type"] == "done"
    assert done["mode"] == "mock"
    assert done["duration_s"] == 2.5
    assert any(e["type"] == "interim" for e in events)
    logged = json.load(open(log, encoding="utf-8"))
    assert len(logged) == 1 and logged[0]["transcript"] == done["transcript"]


def test_no_audio_is_not_logged(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    log = tmp_path / "transcripts.json"
    monkeypatch.setattr(transcript_log, "LOG_PATH", log)
    with TestClient(app).websocket_connect("/ws/transcribe") as ws:
        ws.receive_json()
        ws.send_text("end")
        done = ws.receive_json()
    assert done["type"] == "done" and done["duration_s"] == 0
    assert not log.exists()
