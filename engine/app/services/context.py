# F-M7.5 Application context: settings, repository, adapters and the sim clock, created once at startup.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.adapters.elevenlabs import ElevenLabsAdapter
from app.adapters.gemini import GeminiAdapter
from app.adapters.presage import PresageAdapter
from app.adapters.storage import StorageAdapter
from app.config import Settings
from app.core.clock import Clock, clock
from app.db import Repo, make_repo
from app.models import AdapterStatus


class AppError(Exception):
    """Domain error rendered as {"error": {"code", "message"}} by the global handler (F-M7.7)."""

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
    presage: PresageAdapter
    clock: Clock
    scan_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    guidance_cache: dict[str, Any] = field(default_factory=dict)

    def adapter_status(self) -> AdapterStatus:
        return AdapterStatus(
            presage=self.presage.status,
            gemini=self.gemini.status,
            elevenlabs=self.elevenlabs.status,
            storage=self.storage.status,
        )


_services: Services | None = None


def build_services(settings: Settings) -> Services:
    storage = StorageAdapter(settings)
    return Services(
        settings=settings,
        repo=make_repo(settings.database_url, settings.use_memory_db),
        storage=storage,
        gemini=GeminiAdapter(settings),
        elevenlabs=ElevenLabsAdapter(settings, storage),
        presage=PresageAdapter(settings),
        clock=clock,
    )


def set_services(svc: Services | None) -> None:
    global _services
    _services = svc


def get_services() -> Services:
    if _services is None:
        raise RuntimeError("services not initialised")
    return _services
