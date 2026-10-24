# F-M5.1 Speech-to-text (Scribe) · F-M5.2 Text-to-speech — ElevenLabs REST via httpx. Mock / failure: STT returns
# scenario text; TTS returns audio_url=None so the browser falls back to window.speechSynthesis.
from __future__ import annotations

import hashlib
import logging

import httpx

from app.adapters.storage import StorageAdapter
from app.config import Settings

log = logging.getLogger("atollcare.elevenlabs")
API = "https://api.elevenlabs.io/v1"
# Public premade voices used only when the env does not specify one (team: set ELEVENLABS_VOICE_* explicitly).
DEFAULT_VOICES = {"guide": "21m00Tcm4TlvDq8ikWAM", "status": "JBFqnCBsd6RMkjVDRZzb"}


class ElevenLabsAdapter:
    def __init__(self, settings: Settings, storage: StorageAdapter) -> None:
        self.settings = settings
        self.storage = storage
        self.mode = settings.elevenlabs_mode
        if self.mode == "real" and not settings.elevenlabs_api_key:
            log.warning("ELEVENLABS_MODE=real but ELEVENLABS_API_KEY missing — using mock")
            self.mode = "mock"

    @property
    def status(self) -> str:
        return "real" if self.mode == "real" else "mock"

    def voice_id(self, voice: str) -> str:
        configured = self.settings.elevenlabs_voice_guide if voice == "guide" else self.settings.elevenlabs_voice_status
        return configured or DEFAULT_VOICES[voice]

    async def transcribe(
        self, audio: bytes, filename: str, content_type: str, language: str | None, mock_text: str
    ) -> tuple[str, str, float | None, str]:
        """Returns (text, language, confidence, source)."""
        if self.mode != "real":
            return mock_text, language or "en", 0.99, "mock"
        data = {"model_id": self.settings.elevenlabs_stt_model}
        if language:
            data["language_code"] = language
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{API}/speech-to-text",
                    headers={"xi-api-key": self.settings.elevenlabs_api_key},
                    data=data,
                    files={"file": (filename, audio, content_type)},
                )
            resp.raise_for_status()
            body = resp.json()
            return body.get("text", "").strip(), body.get("language_code") or language or "en", body.get(
                "language_probability"
            ), "elevenlabs"
        except Exception as exc:  # noqa: BLE001
            log.warning("ElevenLabs STT failed: %s", exc)
            raise

    async def speak(self, text: str, voice: str, language: str | None) -> str | None:
        """Returns an audio URL (cached by sha256(text+voice+model)) or None → browser speechSynthesis fallback."""
        if self.mode != "real":
            return None
        model = self.settings.elevenlabs_tts_model
        voice_id = self.voice_id(voice)
        digest = hashlib.sha256(f"{text}|{voice_id}|{model}|{language or ''}".encode()).hexdigest()[:32]
        key = f"tts/{digest}.mp3"
        try:
            if await self.storage.exists(key):
                return self.storage.url(key)
            payload: dict = {"text": text, "model_id": model}
            if language and model.startswith(("eleven_turbo_v2_5", "eleven_flash_v2_5")):
                payload["language_code"] = language
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{API}/text-to-speech/{voice_id}",
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": self.settings.elevenlabs_api_key, "accept": "audio/mpeg"},
                    json=payload,
                )
            resp.raise_for_status()
            return await self.storage.put(key, resp.content, "audio/mpeg")
        except Exception as exc:  # noqa: BLE001
            log.warning("ElevenLabs TTS failed: %s", exc)
            return None
