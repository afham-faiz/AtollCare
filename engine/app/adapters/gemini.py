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


class GeminiComplaint(BaseModel):
    complaint: str


BRIEFING_SYSTEM = """You write a live SBAR handover for the hospital team receiving an emergency transfer.
Rules:
- At most 110 words across the four fields. Plain clinical English, no markdown.
- Use ONLY facts in the JSON. Never invent vitals, history, times or drugs. Say "not recorded" when missing.
- Contactless values (source "presage") are camera estimates; if a value has a flag, mention it needs confirmation.
- Values with source "simulated" are simulated for a demo, not measurements: always write "(simulated)" after them.
- suspected_condition: a short working impression supported by the JSON, or null.
- recommendation: what the receiving team should prepare (team, imaging, theatre, blood), not treatment orders."""

COMPLAINT_SYSTEM = """A companion has described, in their own words, a person who suddenly became unwell.
Write ONE short line (under 100 characters) for an emergency transfer's "what's happening" field: the main problem and
how long, in plain clinical English. Use only what the account says. No diagnosis, no advice, no names."""

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
            # one client for the whole engine: AI Studio or Agent Platform keys (GEMINI_USE_ENTERPRISE), with timeouts
            from app.intake.gemini_client import make_client

            self._client = make_client(api_key=self.settings.gemini_api_key)
        return self._client

    async def _generate(
        self, system: str, prompt: str, schema: type[BaseModel], timeout_s: float, fast_first: bool = False
    ) -> tuple[BaseModel | None, str | None]:
        if self.mode != "real":
            return None, "Gemini in mock mode"
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=0.2,
        )
        order = (self.settings.gemini_model, self.settings.gemini_fallback_model)
        models = list(dict.fromkeys(m for m in (order[::-1] if fast_first else order) if m))
        last_error = "unknown error"
        for model in models:
            for attempt in range(2):  # invalid JSON → retry the same model once
                try:
                    resp = await asyncio.wait_for(
                        self._get_client().aio.models.generate_content(model=model, contents=prompt, config=config),
                        timeout=timeout_s,
                    )
                    return schema.model_validate_json(resp.text or ""), None
                except TimeoutError:
                    last_error = f"Gemini ({model}) timed out after {timeout_s:g} s"
                except ValidationError as exc:
                    last_error = f"Gemini ({model}) returned invalid JSON ({exc.error_count()} errors)"
                    log.warning("gemini attempt %s failed: %s", attempt + 1, last_error)
                    continue
                except Exception as exc:  # noqa: BLE001 — overloaded, unavailable, quota: try the fallback model
                    last_error = f"Gemini ({model}) error: {type(exc).__name__}: {str(exc)[:160]}"
                log.warning("gemini %s failed: %s", model, last_error)
                break
        return None, last_error

    async def briefing(self, data: dict[str, Any]) -> tuple[GeminiBriefing | None, str | None]:
        result, err = await self._generate(
            BRIEFING_SYSTEM, json.dumps(data, default=str, ensure_ascii=False), GeminiBriefing, self.settings.gemini_timeout_s
        )
        return result, err  # type: ignore[return-value]

    async def condense_account(self, account: str) -> str | None:
        """One line for the transfer's complaint, from the companion's own words. None → caller's plain fallback."""
        budget = self.settings.gemini_extract_timeout_s
        try:
            result, _err = await asyncio.wait_for(
                self._generate(COMPLAINT_SYSTEM, account, GeminiComplaint, budget, fast_first=True), timeout=budget)
        except TimeoutError:
            return None
        text = (result.complaint.strip() if result else "")  # type: ignore[union-attr]
        return text[:140] or None

    async def extract(self, text: str) -> tuple[GeminiExtraction | None, str | None]:
        """The crew is watching a spinner: lighter model first, one overall deadline, then the caller's rules."""
        budget = self.settings.gemini_extract_timeout_s
        try:
            result, err = await asyncio.wait_for(
                self._generate(EXTRACT_SYSTEM, text, GeminiExtraction, budget, fast_first=True), timeout=budget
            )
        except TimeoutError:
            return None, f"Gemini extraction took longer than {budget:g} s"
        return result, err  # type: ignore[return-value]
