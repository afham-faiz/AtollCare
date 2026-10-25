from datetime import datetime, timezone
from pathlib import Path

from src.services.json_log import append_log, read_log

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "transcripts.json"


def log_transcript(result: dict) -> Path:
    """Append one finished transcription to logs/transcripts.json (a JSON array)."""
    append_log(LOG_PATH, {"logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **result})
    return LOG_PATH


def read_transcripts(limit: int = 20) -> list[dict]:
    """Most recent first."""
    return read_log(LOG_PATH)[-limit:][::-1]
