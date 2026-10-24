from datetime import datetime
from pathlib import Path

from src import config

RECORDINGS_DIR = config.ROOT / "recordings"


def save_recording(kind: str, data: bytes, ext: str, label: str = "") -> str | None:
    """Keep one trial's media for replay. Returns its URL path (e.g. /recordings/voice_...wav), or None if off."""
    if not data or not config.SAVE_RECORDINGS:
        return None
    RECORDINGS_DIR.mkdir(exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in Path(label).stem)[:40]
    name = f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}" + (f"_{safe}" if safe else "") + f".{ext}"
    path = RECORDINGS_DIR / name
    n = 1
    while path.exists():  # two trials in the same second
        path = RECORDINGS_DIR / f"{path.stem}_{n}{path.suffix}"
        n += 1
    path.write_bytes(data)
    return f"/recordings/{path.name}"
