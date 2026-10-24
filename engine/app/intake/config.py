"""Settings for the intake (Part 1) services, read from the repo-root .env that the engine uses.

The names are the ones Percy's services were written against (GEMINI_VQA_MODEL, VQA_MODE, ...), so those modules
and their tests work unchanged. Values come from the process environment first, then the .env file, then the
defaults below (his env.example). Read on access, so tests can patch them and a restart picks up .env edits.

Gemini is only "on" for intake when the engine's GEMINI_MODE is real: GEMINI_API_KEY reads as blank otherwise, which
is how every intake service switches to its safe no-model behaviour (and how tests never call Google).
"""
import os
import sys
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parents[3]  # repo root
ENV_FILE = ROOT / ".env"

DEFAULTS = {
    "GEMINI_USE_ENTERPRISE": "false",
    "GEMINI_TIMEOUT_S": "150",
    "GEMINI_RETRY_ATTEMPTS": "2",
    "GEMINI_STT_MODEL": "gemini-3.8-flash",
    "GEMINI_STT_FALLBACK_MODEL": "",
    "GEMINI_CHAT_MODEL": "gemini-3.8-flash",
    "GEMINI_ID_MODEL": "gemini-3.8-flash",
    "GEMINI_CUE_PLANNER_MODEL": "gemini-3.8-flash",
    "GEMINI_VQA_MODEL": "gemini-3.8-flash",
    "VQA_FRAME_INTERVAL_S": "2",
    "VQA_MAX_FRAMES": "24",
    "VQA_MODE": "one_pass",
    # How hard Gemini thinks before answering the sign checklist. "low" keeps a 60 s clip to well under a minute;
    # "default" leaves it to the model (slower, sometimes by minutes).
    "GEMINI_VQA_THINKING": "low",
    "VIDEO_RECORD_MAX_S": "60",
    "TRANSCRIBE_LANGUAGE": "en-US",
    "STT_SILENCE_STOP_S": "2",
    "STT_FLASH_PAUSE_S": "0.8",
    "STT_FLASH_MAX_SEGMENT_S": "8",
    "SAVE_RECORDINGS": "false",
}


class ConfigError(RuntimeError):
    pass


@lru_cache
def _file() -> dict[str, str]:
    return {k: v for k, v in dotenv_values(ENV_FILE).items() if v is not None} if ENV_FILE.exists() else {}


def _text(name: str) -> str:
    """Environment, then .env, with no default: what the operator actually set."""
    value = os.environ.get(name)
    return (value if value is not None else _file().get(name, "")).strip()


def _setting(name: str) -> str:
    return _text(name) or DEFAULTS.get(name, "")


def _required(name: str) -> str:
    value = _text(name)
    if not value:
        raise ConfigError(f"{name} is not set. Add a line {name}=... to {ENV_FILE}")
    return value


def _required_float(name: str) -> float:
    raw = _required(name)
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} in {ENV_FILE} is not a number") from None


def _required_choice(name: str, choices: tuple[str, ...]) -> str:
    raw = _required(name).lower()
    if raw not in choices:
        raise ConfigError(f"{name}={raw!r} in {ENV_FILE} must be one of: {', '.join(choices)}")
    return raw


def _required_bool(name: str) -> bool:
    raw = _required(name).lower()
    if raw in ("true", "yes", "on", "1"):
        return True
    if raw in ("false", "no", "off", "0"):
        return False
    raise ConfigError(f"{name}={raw!r} in {ENV_FILE} must be true or false")


def _float(name: str) -> float:
    raw = _setting(name)
    try:
        return float(raw)
    except ValueError:
        raise ConfigError(f"{name}={raw!r} in {ENV_FILE} is not a number") from None


def _choice(name: str, choices: tuple[str, ...]) -> str:
    raw = _setting(name).lower()
    if raw not in choices:
        raise ConfigError(f"{name}={raw!r} in {ENV_FILE} must be one of: {', '.join(choices)}")
    return raw


def _bool(name: str) -> bool:
    raw = _setting(name).lower()
    if raw in ("true", "yes", "on", "1"):
        return True
    if raw in ("false", "no", "off", "0", ""):
        return False
    raise ConfigError(f"{name}={raw!r} in {ENV_FILE} must be true or false")


def _gemini_key() -> str:
    from app.config import get_settings

    s = get_settings()
    return s.gemini_api_key.strip() if s.gemini_mode == "real" else ""


def __getattr__(name: str):
    """Settings are looked up on access, so tests can patch them and nothing is read at import time."""
    settings = {
        "GEMINI_API_KEY": _gemini_key,
        "GEMINI_USE_ENTERPRISE": lambda: _bool("GEMINI_USE_ENTERPRISE"),
        "GEMINI_TIMEOUT_S": lambda: _float("GEMINI_TIMEOUT_S"),
        "GEMINI_RETRY_ATTEMPTS": lambda: max(1, int(_float("GEMINI_RETRY_ATTEMPTS"))),
        "GEMINI_STT_MODEL": lambda: _setting("GEMINI_STT_MODEL"),
        "GEMINI_STT_FALLBACK_MODEL": lambda: _setting("GEMINI_STT_FALLBACK_MODEL"),  # blank = no backup
        "GEMINI_CHAT_MODEL": lambda: _setting("GEMINI_CHAT_MODEL"),
        "GEMINI_ID_MODEL": lambda: _setting("GEMINI_ID_MODEL"),
        "GEMINI_CUE_PLANNER_MODEL": lambda: _setting("GEMINI_CUE_PLANNER_MODEL"),
        "GEMINI_VQA_MODEL": lambda: _setting("GEMINI_VQA_MODEL"),
        "VQA_FRAME_INTERVAL_S": lambda: _float("VQA_FRAME_INTERVAL_S"),
        "VQA_MAX_FRAMES": lambda: int(_float("VQA_MAX_FRAMES")),
        "VQA_MODE": lambda: _choice("VQA_MODE", ("one_pass", "two_step")),
        "GEMINI_VQA_THINKING": lambda: _choice("GEMINI_VQA_THINKING", ("minimal", "low", "medium", "high", "default")),
        "VIDEO_RECORD_MAX_S": lambda: _float("VIDEO_RECORD_MAX_S"),
        "TRANSCRIBE_LANGUAGE": lambda: _setting("TRANSCRIBE_LANGUAGE"),  # blank = auto-detect
        "STT_SILENCE_STOP_S": lambda: _float("STT_SILENCE_STOP_S"),
        "STT_FLASH_PAUSE_S": lambda: _float("STT_FLASH_PAUSE_S"),
        "STT_FLASH_MAX_SEGMENT_S": lambda: _float("STT_FLASH_MAX_SEGMENT_S"),
        "SAVE_RECORDINGS": lambda: _bool("SAVE_RECORDINGS"),
    }
    if name in settings:
        return settings[name]()
    raise AttributeError(name)


def gemini_platform() -> str:
    """'enterprise' (Google Cloud / Agent Platform key) or 'developer' (AI Studio key), from GEMINI_USE_ENTERPRISE."""
    return "enterprise" if sys.modules[__name__].GEMINI_USE_ENTERPRISE else "developer"
