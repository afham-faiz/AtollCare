import asyncio
import io
import json
import wave
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google import genai

from src import config
from src.app import app
from src.services import recordings, results_log, transcript_log, transcription

SECOND = bytes(32000)  # 1 s of 16 kHz 16-bit silence


def wav_upload(seconds: int = 2) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(SECOND * seconds)
    return buf.getvalue()


# ---------------------------------------------------------------- config comes only from .env

def test_missing_setting_is_named_in_the_error(monkeypatch):
    monkeypatch.delenv("GEMINI_STT_MODEL", raising=False)
    with pytest.raises(config.ConfigError, match="GEMINI_STT_MODEL"):
        config._required("GEMINI_STT_MODEL")


def test_non_numeric_setting_is_reported(monkeypatch):
    monkeypatch.setenv("STT_SILENCE_STOP_S", "two")
    with pytest.raises(config.ConfigError, match="STT_SILENCE_STOP_S"):
        config._required_float("STT_SILENCE_STOP_S")


def test_info_reports_a_missing_setting_instead_of_crashing(monkeypatch):
    def boom(model=None):
        raise config.ConfigError("GEMINI_STT_MODEL is not set")
    monkeypatch.setattr(transcription, "stt_method", boom)
    info = transcription.transcription_info()
    assert info["mode"] == "error" and "GEMINI_STT_MODEL" in info["error"]


# ---------------------------------------------------------------- recordings

def test_recordings_are_off_unless_enabled():
    assert recordings.save_recording("voice", b"x", "wav") is None


def test_recordings_keep_every_trial_with_unique_names(monkeypatch):
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)
    first = recordings.save_recording("voice", b"one", "wav")
    second = recordings.save_recording("voice", b"two", "wav")
    assert first != second and first.startswith("/recordings/voice_")
    assert (recordings.RECORDINGS_DIR / first.split("/")[-1]).read_bytes() == b"one"
    assert (recordings.RECORDINGS_DIR / second.split("/")[-1]).read_bytes() == b"two"


def test_recording_label_is_made_filename_safe(monkeypatch):
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)
    url = recordings.save_recording("upload", b"x", "wav", label="my voice/note #1.m4a")
    assert "/" not in url.removeprefix("/recordings/") and "#" not in url


# ---------------------------------------------------------------- audio files

def test_file_transcription_is_sent_in_pieces_for_long_audio(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(transcription, "FILE_PIECE_S", 1)
    seen = []
    monkeypatch.setattr(transcription, "_flash_transcribe",
                        lambda client, pcm, model=None: seen.append(model) or f"part{len(seen)}")
    monkeypatch.setattr(transcription, "make_client", lambda: object())
    result = transcription.transcribe_pcm(SECOND * 3)
    assert result["segments"] == ["part1", "part2", "part3"]
    assert seen == ["gemini-3.8-flash"] * 3
    assert result["transcript"] == "part1 part2 part3" and result["duration_s"] == 3.0


def test_file_transcription_never_uses_a_streaming_model(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-live")
    with pytest.raises(config.ConfigError, match="GEMINI_STT_FALLBACK_MODEL"):
        transcription.transcribe_pcm(SECOND)
    monkeypatch.setattr(config, "GEMINI_STT_FALLBACK_MODEL", "gemini-3.8-flash")
    assert transcription.file_model() == "gemini-3.8-flash"


def test_upload_endpoint_transcribes_saves_and_logs(monkeypatch):
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)  # no key -> mock transcription
    client = TestClient(app)
    resp = client.post("/api/transcribe-file", files={"audio": ("note.wav", wav_upload(2), "audio/wav")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["source"] == "file" and body["filename"] == "note.wav" and body["duration_s"] == 2.0
    assert (recordings.RECORDINGS_DIR / body["audio_file"].split("/")[-1]).exists()
    assert json.load(open(transcript_log.LOG_PATH, encoding="utf-8"))[0]["filename"] == "note.wav"


def test_upload_endpoint_rejects_garbage_and_empty():
    client = TestClient(app)
    assert client.post("/api/transcribe-file", files={"audio": ("x.wav", b"", "audio/wav")}).status_code == 400
    assert client.post("/api/transcribe-file", files={"audio": ("x.wav", b"not audio", "audio/wav")}).status_code == 400


def test_failed_upload_is_still_logged(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-live")  # no backup -> ConfigError
    resp = TestClient(app).post("/api/transcribe-file", files={"audio": ("a.wav", wav_upload(1), "audio/wav")})
    assert resp.status_code == 502
    logged = json.load(open(transcript_log.LOG_PATH, encoding="utf-8"))
    assert "GEMINI_STT_FALLBACK_MODEL" in logged[0]["error"]


# ---------------------------------------------------------------- microphone trials are recorded

def test_microphone_trial_audio_is_saved_and_linked(monkeypatch):
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)
    with TestClient(app).websocket_connect("/ws/transcribe") as ws:
        ws.receive_json()
        for _ in range(10):
            ws.send_bytes(bytes(3200))
        ws.send_text("end")
        events = []
        while not events or events[-1]["type"] not in ("done", "error"):
            events.append(ws.receive_json())
    done = events[-1]
    assert done["type"] == "done" and done["source"] == "microphone"
    saved = recordings.RECORDINGS_DIR / done["audio_file"].split("/")[-1]
    with wave.open(str(saved)) as w:
        assert w.getframerate() == 16000 and w.getnframes() == 16000  # 1 s


# ---------------------------------------------------------------- backup model

def test_backup_model_takes_over_when_main_cannot_start(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-live")
    monkeypatch.setattr(config, "GEMINI_STT_FALLBACK_MODEL", "gemini-3.8-flash")

    class Refusing:
        @asynccontextmanager
        async def connect(self, model, config):
            raise RuntimeError("1008 model not found")
            yield

    monkeypatch.setattr(genai, "Client", lambda **kw: SimpleNamespace(aio=SimpleNamespace(live=Refusing())))
    monkeypatch.setattr(transcription, "make_client", lambda: genai.Client())
    used = []
    monkeypatch.setattr(transcription, "_flash_transcribe", lambda c, pcm, model=None: used.append(model) or "hello there")

    async def run():
        import array, math
        q, events = asyncio.Queue(), []
        for c in range(10):
            q.put_nowait(array.array("h", [int(9000 * math.sin(2 * math.pi * 220 * (c * 1600 + i) / 16000)) for i in range(1600)]).tobytes())
        for _ in range(12):
            q.put_nowait(bytes(3200))
        q.put_nowait(None)

        async def on_event(e):
            events.append(e)
        return await transcription.transcribe_stream(q, on_event), events

    result, events = asyncio.run(run())
    assert result["model"] == "gemini-3.8-flash" and result["fallback_from"] == "gemini-3.8-live"
    assert result["segments"] == ["hello there"] and used == ["gemini-3.8-flash"]
    assert any(e["type"] == "notice" and "gemini-3.8-live" in e["text"] for e in events)


def test_no_backup_means_the_error_surfaces(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-live")

    class Refusing:
        @asynccontextmanager
        async def connect(self, model, config):
            raise RuntimeError("refused")
            yield

    monkeypatch.setattr(transcription, "make_client", lambda: SimpleNamespace(aio=SimpleNamespace(live=Refusing())))

    async def run():
        q = asyncio.Queue()
        q.put_nowait(None)
        return await transcription.transcribe_stream(q, lambda e: asyncio.sleep(0))

    with pytest.raises(RuntimeError, match="refused"):
        asyncio.run(run())


# ---------------------------------------------------------------- video trials are recorded

def test_video_log_entry_links_the_saved_copy(monkeypatch, tmp_path):
    from src.models.schemas import RppgEstimates
    monkeypatch.setattr(results_log, "LOG_PATH", tmp_path / "results.json")
    results_log.log_result("clip.mp4", {"original": 1}, {"presage": 2}, RppgEstimates(), saved_file="/recordings/video_x.mp4")
    assert json.load(open(tmp_path / "results.json", encoding="utf-8"))[0]["video_file"] == "/recordings/video_x.mp4"
