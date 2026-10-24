# Wires services together once at startup; routers depend on get_hub().
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.services.context import Services, build_services
from app.services.demo import DemoService
from app.services.insights import InsightsService
from app.services.transfers import TransferService
from app.sim.loop import SimLoop


@dataclass
class Hub:
    svc: Services
    transfers: TransferService
    demo: DemoService
    insights: InsightsService
    loop: SimLoop


_hub: Hub | None = None


def build_hub(settings: Settings) -> Hub:
    global _hub
    svc = build_services(settings)
    transfers = TransferService(svc)
    _hub = Hub(svc=svc, transfers=transfers, demo=DemoService(svc), insights=InsightsService(svc),
               loop=SimLoop(transfers, settings.sim_tick_s))
    return _hub


def get_hub() -> Hub:
    if _hub is None:
        raise RuntimeError("hub not initialised")
    return _hub
