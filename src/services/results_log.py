from datetime import datetime, timezone
from pathlib import Path

from src.models.schemas import RppgEstimates
from src.services.json_log import append_log, read_log

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "results.json"


def log_result(video_name: str, sizes_mb: dict, seconds: dict, estimates: RppgEstimates,
               saved_file: str | None = None) -> Path:
    """Append one analysis to logs/results.json (a JSON array)."""
    append_log(LOG_PATH, {
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "video": video_name,
        "video_file": saved_file,
        "sizes_mb": sizes_mb,
        "seconds": seconds,
        "result": estimates.model_dump(),
    })
    return LOG_PATH


def read_history(limit: int = 20) -> list[dict]:
    """Most recent runs first, without the bulky per-sample traces."""
    rows = read_log(LOG_PATH)[-limit:]
    for row in rows:
        row.get("result", {}).pop("diagnostics", None)
    return rows[::-1]
