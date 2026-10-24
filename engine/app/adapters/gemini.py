# F-M2.2 structured intake · F-M2.7 SBAR · F-M2.8 route explanation · F-M5.3 guidance selection — Gemini via
# google-genai with JSON response schemas. Every call has a deterministic fallback in the caller; this adapter
# returns (result | None, error | None) and never raises.
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger("atollcare.gemini")


class GeminiSuspected(BaseModel):
    condition_id: str
    probability: float
    rationale: str


class GeminiIntake(BaseModel):
    language: str
    chief_complaint: str
    symptoms: list[str]
    red_flags: list[str]
    onset_time: str | None
    onset_confidence: Literal["exact", "approx", "unknown"]
    suspected_conditions: list[GeminiSuspected]
    missing_info: list[str]


class GeminiSbar(BaseModel):
    situation: str
    background: str
    assessment: str
    recommendation: str


class GeminiExplanation(BaseModel):
    explanation: str


class GeminiGuidance(BaseModel):
    step_ids: list[str]


INTAKE_SYSTEM = """You are a clinical intake assistant for emergency referrals from remote islands.
Extract structured facts from the reporter's free text. Rules:
- suspected_conditions[].condition_id MUST be one of: {condition_ids} (use "other" if none fit).
- Probabilities are 0–1 and must sum to at most 1.
- Convert relative onset ("2 hours ago", "for 40 minutes") to an absolute ISO 8601 time using the supplied current
  time; null if not stated. onset_confidence: exact | approx | unknown.
- red_flags: short phrases of dangerous features actually mentioned. Never invent findings.
- missing_info: up to 4 short questions a clinician should ask next.
- language: ISO 639-1 code of the input text.
- NEVER give treatment advice."""

SBAR_SYSTEM = """You write SBAR referral summaries for a receiving specialist. Be factual and concise: at most 120
words in total across the four fields. Only use values present in the JSON; write "not recorded" for anything
missing. Do not fabricate vitals, history or findings. No treatment instructions beyond what the JSON states."""

EXPLAIN_SYSTEM = """Explain in at most 3 sentences why the chosen route beats the alternatives. Cite concrete numbers
from the JSON (minutes, modes, constraints such as night or sea state). Plain language for clinicians and
coordinators. Do not add clinical advice."""

GUIDANCE_SYSTEM = """You select and order first-aid steps from a vetted library. Return only step ids from the list
provided, most urgent first, 3–6 ids. You may omit steps that do not apply. NEVER write new instructions."""


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

    async def extract_intake(
        self, raw_text: str, now: datetime, condition_ids: list[str], context: dict[str, Any]
    ) -> tuple[GeminiIntake | None, str | None]:
        system = INTAKE_SYSTEM.format(condition_ids=", ".join(condition_ids + ["other"]))
        prompt = json.dumps(
            {"current_time": now.isoformat(), "context": context, "reporter_text": raw_text}, ensure_ascii=False
        )
        result, err = await self._generate(system, prompt, GeminiIntake)
        if result is None:
            return None, err
        intake: GeminiIntake = result  # type: ignore[assignment]
        allowed = set(condition_ids) | {"other"}
        intake.suspected_conditions = [s for s in intake.suspected_conditions if s.condition_id in allowed]
        total = sum(s.probability for s in intake.suspected_conditions)
        if total > 1:
            for s in intake.suspected_conditions:
                s.probability = round(s.probability / total, 2)
        return intake, None

    async def sbar(self, case_json: dict[str, Any]) -> tuple[GeminiSbar | None, str | None]:
        result, err = await self._generate(SBAR_SYSTEM, json.dumps(case_json, default=str), GeminiSbar)
        return result, err  # type: ignore[return-value]

    async def explain(self, routes_json: dict[str, Any]) -> tuple[str | None, str | None]:
        result, err = await self._generate(EXPLAIN_SYSTEM, json.dumps(routes_json, default=str), GeminiExplanation)
        return (result.explanation if result else None), err  # type: ignore[union-attr]

    async def select_guidance(
        self, condition_id: str, role: str, steps: list[dict[str, str]], summary: dict[str, Any]
    ) -> tuple[list[str] | None, str | None]:
        prompt = json.dumps({"condition": condition_id, "role": role, "case": summary, "library": steps}, default=str)
        result, err = await self._generate(GUIDANCE_SYSTEM, prompt, GeminiGuidance)
        if result is None:
            return None, err
        allowed = [s["id"] for s in steps]
        ids = [i for i in result.step_ids if i in allowed]  # type: ignore[union-attr]
        return (list(dict.fromkeys(ids)) or None), None
