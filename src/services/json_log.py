import json
import os
import tempfile
import threading
from pathlib import Path

_lock = threading.Lock()


def read_log(path: Path) -> list[dict]:
    """Return the log as a list (oldest first). A missing or unreadable file reads as empty."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return data if isinstance(data, list) else []


def append_log(path: Path, entry: dict) -> None:
    """Append one entry to a log kept as a single, valid JSON array (readable with json.load)."""
    path.parent.mkdir(exist_ok=True)
    with _lock:
        entries = read_log(path)
        entries.append(entry)
        # Write to a temp file then swap, so a crash never leaves half a file.
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2)
        os.replace(tmp, path)
