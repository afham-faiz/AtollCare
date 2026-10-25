from datetime import datetime, timezone
from pathlib import Path

from src.models.schemas import VisualCueReport
from src.services.json_log import append_log, read_log

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "visual_cues.json"


def log_visual_cues(video_name: str, transcript: str, report: VisualCueReport,
                    evidence_files: dict[int, str | None]) -> Path:
    """Append one session to logs/visual_cues.json (a JSON array)."""
    append_log(LOG_PATH, {
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "video": video_name,
        "transcript": transcript,
        "evidence_files": {str(i): url for i, url in evidence_files.items()},
        "report": report.model_dump(),
    })
    return LOG_PATH


def read_visual_cues(limit: int = 20) -> list[dict]:
    """Most recent first."""
    return read_log(LOG_PATH)[-limit:][::-1]
