"""Reads inputs/.env (git-ignored). The file takes priority over Windows environment variables.

There are deliberately NO default model names or tuning numbers in code: everything is set in
inputs/.env. A missing setting raises ConfigError naming the line to add. Settings are read when
the app starts, so restart the server after editing inputs/.env.
"""
import os
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


def __getattr__(name: str):
    """Settings are looked up on access, so an unset one fails only when something needs it."""
    optional = {
        "GEMINI_API_KEY": lambda: _text("GEMINI_API_KEY"),
        "GEMINI_PLATFORM": lambda: _text("GEMINI_PLATFORM").lower() or "auto",
        "GEMINI_STT_FALLBACK_MODEL": lambda: _text("GEMINI_STT_FALLBACK_MODEL"),   # blank = no backup
        "TRANSCRIBE_LANGUAGE": lambda: _text("TRANSCRIBE_LANGUAGE"),               # blank = auto-detect
        "SAVE_RECORDINGS": lambda: _text("SAVE_RECORDINGS").lower() in ("1", "true", "yes", "on"),
    }
    required = {
        "GEMINI_STT_MODEL": lambda: _required("GEMINI_STT_MODEL"),
        "GEMINI_CHAT_MODEL": lambda: _required("GEMINI_CHAT_MODEL"),
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
    """'developer' (AI Studio key) or 'enterprise' (Google Cloud / Vertex AI key)."""
    platform = __getattr__("GEMINI_PLATFORM")
    if platform in ("developer", "enterprise"):
        return platform
    return "developer" if __getattr__("GEMINI_API_KEY").startswith("AIza") else "enterprise"
