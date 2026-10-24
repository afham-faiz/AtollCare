import array
import asyncio
import math
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
from google import genai

from app.intake import config, transcription


def pcm(seconds: float, loud: bool) -> list[bytes]:
    """100 ms chunks of a 220 Hz tone (loud) or silence."""
    chunks = []
    for c in range(round(seconds * 10)):
        samples = array.array("h", [
            int(12000 * math.sin(2 * math.pi * 220 * (c * 1600 + i) / 16000)) if loud else 0 for i in range(1600)
        ])
        chunks.append(samples.tobytes())
    return chunks


async def run(chunks):
    q: asyncio.Queue = asyncio.Queue()
    for c in chunks:
        q.put_nowait(c)
    q.put_nowait(None)
    events = []

    async def on_event(e):
        events.append(e)

    return await transcription.transcribe_stream(q, on_event), events


def test_method_is_chosen_from_the_model_name(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-live")
    assert transcription.stt_method() == "live"
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-flash")
    assert transcription.stt_method() == "flash"
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    assert transcription.stt_method() == "mock"


def test_flash_sends_one_request_per_sentence_in_order(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(config, "STT_FLASH_PAUSE_S", 0.8)
    calls = []

    def fake_transcribe(client, pcm_bytes, model=None):
        calls.append(len(pcm_bytes))
        return f"sentence {len(calls)}"

    monkeypatch.setattr(transcription, "_flash_transcribe", fake_transcribe)
    chunks = pcm(1.0, True) + pcm(1.2, False) + pcm(1.0, True) + pcm(1.2, False) + pcm(2, False)
    result, events = asyncio.run(run(chunks))

    assert result["segments"] == ["sentence 1", "sentence 2"]
    assert result["transcript"] == "sentence 1 sentence 2"
    assert result["mode"] == "gemini" and result["model"] == "gemini-3.8-flash"
    assert [e["text"] for e in events if e["type"] == "final"] == ["sentence 1", "sentence 2"]
    assert len(calls) == 2  # leading/trailing silence is never sent


def test_flash_splits_very_long_speech(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(config, "STT_FLASH_MAX_SEGMENT_S", 3.0)
    monkeypatch.setattr(transcription, "_flash_transcribe", lambda client, p, model=None: "piece")
    result, _ = asyncio.run(run(pcm(7.0, True)))
    assert len(result["segments"]) >= 2


def test_flash_ignores_silence_only(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-flash")
    monkeypatch.setattr(transcription, "_flash_transcribe", lambda c, p, model=None: pytest.fail("should not be called"))
    result, _ = asyncio.run(run(pcm(3.0, False)))
    assert result["segments"] == []


@pytest.mark.parametrize("reply, expected", [
    ("NO_SPEECH", ""),
    ("  no speech ", ""),
    ("My father fell down.", "My father fell down."),
    ("", ""),
])
def test_flash_drops_no_speech_answers(reply, expected):
    client = SimpleNamespace(models=SimpleNamespace(generate_content=lambda **kw: SimpleNamespace(text=reply)))
    assert transcription._flash_transcribe(client, bytes(3200)) == expected


class FakeLive:
    """Stands in for client.aio.live.connect(): fragments, then turn_complete."""

    def __init__(self, script):
        self.script, self.sent, self.ended = script, [], False

    @asynccontextmanager
    async def connect(self, model, config):
        self.model, self.config = model, config
        yield self

    async def send_realtime_input(self, **kw):
        if kw.get("audio_stream_end"):
            self.ended = True
        else:
            self.sent.append(kw["audio"].data)

    async def receive(self):
        while not self.sent:
            await asyncio.sleep(0.01)
        for content in self.script:
            yield SimpleNamespace(server_content=SimpleNamespace(
                interim_input_transcription=None, input_transcription=content.get("text") and SimpleNamespace(text=content["text"]),
                turn_complete=content.get("turn_complete", False), generation_complete=False))
        await asyncio.sleep(10)  # a live session stays open; the code must stop on its own


def fake_client(live):
    return lambda **kwargs: SimpleNamespace(aio=SimpleNamespace(live=live))


def test_live_joins_fragments_and_finalises_on_turn_complete(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-live")
    live = FakeLive([{"text": "My father"}, {"text": " fell down"}, {"turn_complete": True}])
    monkeypatch.setattr(genai, "Client", fake_client(live))

    result, events = asyncio.run(run(pcm(0.5, True)))

    assert result["segments"] == ["My father fell down"]
    assert live.ended and live.model == "gemini-3.8-live"
    interim = [e["text"] for e in events if e["type"] == "interim"]
    assert interim == ["My father", "My father fell down"]
    # native-audio models only accept AUDIO output; the config must also silence the model
    assert list(live.config.response_modalities) == ["AUDIO"]
    assert "silent" in live.config.system_instruction


def test_live_finalises_leftover_text_when_no_turn_complete_arrives(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "GEMINI_STT_MODEL", "gemini-3.8-live")
    monkeypatch.setattr(transcription, "FINAL_GRACE_S", 0.3)
    live = FakeLive([{"text": "no turn end"}])
    monkeypatch.setattr(genai, "Client", fake_client(live))
    result, _ = asyncio.run(run(pcm(0.5, True)))
    assert result["segments"] == ["no turn end"]
