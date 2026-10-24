# Gemini adapter resilience: an overloaded primary model falls back; extraction never keeps the crew waiting.
import asyncio
import json
from types import SimpleNamespace

from app.adapters.gemini import GeminiAdapter
from app.config import Settings


def adapter(behaviour):
    """behaviour: model name → JSON string to return, an exception to raise, or a float to sleep (seconds)."""
    calls: list[str] = []

    async def generate_content(model, contents, config):
        calls.append(model)
        b = behaviour[model]
        if isinstance(b, Exception):
            raise b
        if isinstance(b, float):
            await asyncio.sleep(b)
        return SimpleNamespace(text=b if isinstance(b, str) else "{}")

    a = GeminiAdapter(Settings(gemini_mode="real", gemini_api_key="test", gemini_model="primary",
                               gemini_fallback_model="lite", gemini_extract_timeout_s=0.3))
    a._client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)))
    return a, calls


EXTRACTION = json.dumps({"observations": ["Pain 8/10"], "interventions": ["Aspirin 300 mg"]})
BRIEFING = json.dumps({"situation": "s", "background": "b", "assessment": "a", "recommendation": "r",
                       "suspected_condition": None})


def test_overloaded_primary_falls_back_to_lite_for_the_briefing():
    a, calls = adapter({"primary": RuntimeError("503 UNAVAILABLE"), "lite": BRIEFING})
    result, err = asyncio.run(a.briefing({"x": 1}))
    assert err is None and result.situation == "s"
    assert calls == ["primary", "lite"]


def test_extraction_tries_the_fast_model_first_and_respects_its_deadline():
    a, calls = adapter({"lite": EXTRACTION, "primary": EXTRACTION})
    result, err = asyncio.run(a.extract("gave aspirin"))
    assert err is None and result.interventions == ["Aspirin 300 mg"] and calls == ["lite"]

    slow, _ = adapter({"lite": 5.0, "primary": 5.0})
    result, err = asyncio.run(slow.extract("gave aspirin"))
    assert result is None and "longer than" in err  # the caller then uses the rule-based extractor
