"""Reads inputs/.env (git-ignored). The file takes priority over Windows environment variables.

There are deliberately NO default model names or tuning numbers in code: everything is set in
inputs/.env. A missing setting raises ConfigError naming the line to add. Settings are read when
the app starts, so restart the server after editing inputs/.env.
"""
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / "inputs" / ".env"
load_dotenv(ENV_FILE, override=True)


class ConfigError(RuntimeError):
    pass


def _text(name: str) -> str:
    return os.environ.get(name, "").strip()


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


def __getattr__(name: str):
    """Settings are looked up on access, so an unset one fails only when something needs it."""
    optional = {
        "GEMINI_API_KEY": lambda: _text("GEMINI_API_KEY"),
        "GEMINI_STT_FALLBACK_MODEL": lambda: _text("GEMINI_STT_FALLBACK_MODEL"),   # blank = no backup
        "TRANSCRIBE_LANGUAGE": lambda: _text("TRANSCRIBE_LANGUAGE"),               # blank = auto-detect
        "SAVE_RECORDINGS": lambda: _text("SAVE_RECORDINGS").lower() in ("1", "true", "yes", "on"),
    }
    required = {
        "GEMINI_USE_ENTERPRISE": lambda: _required_bool("GEMINI_USE_ENTERPRISE"),
        "GEMINI_STT_MODEL": lambda: _required("GEMINI_STT_MODEL"),
        "GEMINI_CHAT_MODEL": lambda: _required("GEMINI_CHAT_MODEL"),
        "GEMINI_ID_MODEL": lambda: _required("GEMINI_ID_MODEL"),
        "GEMINI_CUE_PLANNER_MODEL": lambda: _required("GEMINI_CUE_PLANNER_MODEL"),
        "GEMINI_VQA_MODEL": lambda: _required("GEMINI_VQA_MODEL"),
        "VQA_FRAME_INTERVAL_S": lambda: _required_float("VQA_FRAME_INTERVAL_S"),
        "VQA_MAX_FRAMES": lambda: int(_required_float("VQA_MAX_FRAMES")),
        "VQA_MODE": lambda: _required_choice("VQA_MODE", ("one_pass", "two_step")),
        "VIDEO_RECORD_MAX_S": lambda: _required_float("VIDEO_RECORD_MAX_S"),
        "STT_SILENCE_STOP_S": lambda: _required_float("STT_SILENCE_STOP_S"),
        "STT_FLASH_PAUSE_S": lambda: _required_float("STT_FLASH_PAUSE_S"),
        "STT_FLASH_MAX_SEGMENT_S": lambda: _required_float("STT_FLASH_MAX_SEGMENT_S"),
    }
    if name in optional:
        return optional[name]()
    if name in required:
        return required[name]()
    raise AttributeError(name)


def gemini_platform() -> str:
    """'enterprise' (Google Cloud / Agent Platform key) or 'developer' (AI Studio key), from GEMINI_USE_ENTERPRISE."""
    return "enterprise" if getattr(sys.modules[__name__], "GEMINI_USE_ENTERPRISE") else "developer"
