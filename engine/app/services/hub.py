# Wires services together once at startup; routers depend on get_hub().
from __future__ import annotations

from dataclasses import dataclass

from app.config import Settings
from app.services.cases import CaseService
from app.services.context import Services, build_services, set_services
from app.services.scans import ScanService
from app.services.scenarios import ScenarioService
from app.services.world import WorldService
from app.sim.transport_sim import TransportSimulator


@dataclass
class Hub:
    svc: Services
    cases: CaseService
    scans: ScanService
    world: WorldService
    scenarios: ScenarioService
    sim: TransportSimulator


_hub: Hub | None = None


def build_hub(settings: Settings) -> Hub:
    global _hub
    svc = build_services(settings)
    set_services(svc)
    cases = CaseService(svc)
    world = WorldService(svc, cases)
    scenarios = ScenarioService(svc, cases, world)
    _hub = Hub(
        svc=svc,
        cases=cases,
        scans=ScanService(svc, cases),
        world=world,
        scenarios=scenarios,
        sim=TransportSimulator(cases, scenarios, settings.sim_tick_s),
    )
    return _hub


def get_hub() -> Hub:
    if _hub is None:
        raise RuntimeError("hub not initialised")
    return _hub
