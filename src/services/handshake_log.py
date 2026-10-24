from datetime import datetime, timezone
from pathlib import Path

from src.models.schemas import HandshakeResult, PreArrivalPacket
from src.services.json_log import append_log, read_log

LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "handshakes.json"


def log_handshake(packet: PreArrivalPacket, route: dict, result: HandshakeResult) -> Path:
    """Append one hand-off to logs/handshakes.json (a JSON array). The packet holds no name or ID number."""
    append_log(LOG_PATH, {
        "logged_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "route": route,
        "packet": packet.model_dump(),
        "result": result.model_dump(),
    })
    return LOG_PATH


def read_handshakes(limit: int = 20) -> list[dict]:
    """Most recent first."""
    return read_log(LOG_PATH)[-limit:][::-1]
