# Gemini via google-genai with JSON response schemas: (1) live SBAR briefing for the receiving team,
# (2) extraction of interventions / observations from crew voice notes. Every call has a deterministic fallback in
# the caller; this adapter returns (result | None, error | None) and never raises.
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger("atollcare.gemini")


class GeminiBriefing(BaseModel):
    situation: str
    background: str
    assessment: str
    recommendation: str
    suspected_condition: str | None


class GeminiExtraction(BaseModel):
    observations: list[str]
    interventions: list[str]


BRIEFING_SYSTEM = """You write a live SBAR handover for the hospital team receiving an emergency transfer.
Rules:
- At most 110 words across the four fields. Plain clinical English, no markdown.
- Use ONLY facts in the JSON. Never invent vitals, history, times or drugs. Say "not recorded" when missing.
- Contactless values (source "presage") are camera estimates; if a value has a flag, mention it needs confirmation.
- Values with source "simulated" are a demo signal, not measurements: always write "(demo signal)" after them.
- suspected_condition: a short working impression supported by the JSON, or null.
- recommendation: what the receiving team should prepare (team, imaging, theatre, blood), not treatment orders."""

EXTRACT_SYSTEM = """Extract from an ambulance crew's spoken note:
- interventions: things the crew DID (drugs with dose, oxygen, fluids, procedures), short, e.g. "Aspirin 300 mg".
- observations: clinical findings or symptoms, short, e.g. "Pain 8/10", "ST elevation inferior leads".
Only include what is explicitly said. Empty lists if nothing applies."""


class GeminiAdapter:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.mode = settings.gemini_mode
        if self.mode == "real" and not settings.gemini_api_key:
            log.warning("GEMINI_MODE=real but GEMINI_API_KEY missing — using mock")
            self.mode = "mock"
        self._client = None

    @property
    def status(self) -> str:
        return "real" if self.mode == "real" else "mock"

    def _get_client(self):
        if self._client is None:
            from google import genai

            self._client = genai.Client(api_key=self.settings.gemini_api_key)
        return self._client

    async def _generate(self, system: str, prompt: str, schema: type[BaseModel]) -> tuple[BaseModel | None, str | None]:
        if self.mode != "real":
            return None, "Gemini in mock mode"
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        )
        last_error = "unknown error"
        for attempt in range(2):  # validate, retry once
            try:
                resp = await asyncio.wait_for(
                    self._get_client().aio.models.generate_content(
                        model=self.settings.gemini_model, contents=prompt, config=config
                    ),
                    timeout=self.settings.gemini_timeout_s,
                )
                return schema.model_validate_json(resp.text or ""), None
            except asyncio.TimeoutError:
                last_error = f"Gemini timed out after {self.settings.gemini_timeout_s:g} s"
                break
            except ValidationError as exc:
                last_error = f"Gemini returned invalid JSON ({exc.error_count()} errors)"
            except Exception as exc:  # noqa: BLE001
                last_error = f"Gemini error: {type(exc).__name__}: {str(exc)[:160]}"
            log.warning("gemini attempt %s failed: %s", attempt + 1, last_error)
        return None, last_error

    async def briefing(self, data: dict[str, Any]) -> tuple[GeminiBriefing | None, str | None]:
        result, err = await self._generate(BRIEFING_SYSTEM, json.dumps(data, default=str, ensure_ascii=False), GeminiBriefing)
        return result, err  # type: ignore[return-value]

    async def extract(self, text: str) -> tuple[GeminiExtraction | None, str | None]:
        result, err = await self._generate(EXTRACT_SYSTEM, text, GeminiExtraction)
        return result, err  # type: ignore[return-value]
