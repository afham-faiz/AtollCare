from datetime import datetime, timezone
from pathlib import Path

from src.models.schemas import Demographics
from src.services.json_log import append_log, read_log

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "id_scans.json"


def log_id_scan(filename: str, demographics: Demographics, saved_file: str | None = None) -> Path:
    """Append one ID read to logs/id_scans.json (a JSON array)."""
    append_log(LOG_PATH, {
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "filename": filename,
        "image_file": saved_file,
        "result": demographics.model_dump(),
    })
    return LOG_PATH


def read_id_scans(limit: int = 20) -> list[dict]:
    """Most recent first, without the bulky raw model output."""
    rows = read_log(LOG_PATH)[-limit:]
    for row in rows:
        row.get("result", {}).pop("diagnostics", None)
    return rows[::-1]
