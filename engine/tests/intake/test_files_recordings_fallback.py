import asyncio
import io
import wave
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from google import genai

from app.intake import config, transcription

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


# ---------------------------------------------------------------- microphone trials are recorded


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
        import array
        import math
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

