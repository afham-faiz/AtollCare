# Application context: settings, repository, adapters, sim clock and Presage bridge status, created once at startup.
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from app.adapters.elevenlabs import ElevenLabsAdapter
from app.adapters.gemini import GeminiAdapter
from app.adapters.storage import StorageAdapter
from app.config import Settings
from app.core.clock import Clock, clock, real_now
from app.db import Repo, make_repo
from app.models import AdapterStatus, BridgeHeartbeat, BridgeStatus, InfraStatus

BRIDGE_TIMEOUT = timedelta(seconds=15)


class AppError(Exception):
    """Domain error rendered as {"error": {"code", "message"}} by the global handler."""

    def __init__(self, code: str, message: str, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


@dataclass
class Services:
    settings: Settings
    repo: Repo
    storage: StorageAdapter
    gemini: GeminiAdapter
    elevenlabs: ElevenLabsAdapter
    clock: Clock
    infra: InfraStatus = field(default_factory=lambda: InfraStatus(host="Local", database="In-memory"))
    bridge: BridgeHeartbeat | None = None
    bridge_seen: datetime | None = None
    caches: dict[str, object] = field(default_factory=dict)

    def bridge_status(self) -> BridgeStatus:
        live = self.bridge is not None and self.bridge_seen is not None and real_now() - self.bridge_seen < BRIDGE_TIMEOUT
        return BridgeStatus(
            connected=live,
            sdk=self.bridge.sdk if self.bridge else None,
            version=self.bridge.version if self.bridge else None,
            message=self.bridge.message if self.bridge else None,
            last_seen=self.bridge_seen,
        )

    def adapter_status(self) -> AdapterStatus:
        b = self.bridge_status()
        return AdapterStatus(
            presage="live" if b.connected and b.sdk == "ready" else "simulated",
            gemini=self.gemini.status,  # type: ignore[arg-type]
            elevenlabs=self.elevenlabs.status,  # type: ignore[arg-type]
            storage=self.storage.status,  # type: ignore[arg-type]
        )


def build_services(settings: Settings) -> Services:
    storage = StorageAdapter(settings)
    return Services(
        settings=settings,
        repo=make_repo(settings.database_url, settings.use_memory_db),
        storage=storage,
        gemini=GeminiAdapter(settings),
        elevenlabs=ElevenLabsAdapter(settings, storage),
        clock=clock,
    )
