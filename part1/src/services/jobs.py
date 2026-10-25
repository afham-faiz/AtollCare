"""Run a slow task in the background and let the caller poll for it.

Needed because a request through the Cloudflare tunnel is cut off after about 100 seconds, and a
60 s recording takes longer than that to analyse (Presage plays the clip in real time).
Jobs live in memory only: they are gone when the server restarts.
"""
import threading
import uuid
from typing import Callable

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def start(task: Callable[[], dict]) -> str:
    job_id = uuid.uuid4().hex
    with _lock:
        _jobs[job_id] = {"state": "running"}

    def run() -> None:
        try:
            outcome = {"state": "done", "result": task()}
        except Exception as exc:  # HTTPException carries .detail; anything else is shown as its message
            outcome = {"state": "error", "detail": str(getattr(exc, "detail", None) or f"{exc.__class__.__name__}: {exc}")}
        with _lock:
            _jobs[job_id] = outcome

    threading.Thread(target=run, daemon=True).start()
    return job_id


def get(job_id: str) -> dict | None:
    with _lock:
        return _jobs.get(job_id)
