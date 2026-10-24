# F-M2.4 / F-M2.5 Static reference data loader (facilities, modes, conditions, baseline, first aid, scenarios).
# All illustrative clinical/transport numbers live in app/data — never hard-code them in logic.
import json
from functools import lru_cache
from typing import Any

import yaml

from app.config import DATA_DIR
from app.models import ConditionInfo, Facility, TransportMode, TransportModeInfo


def _yaml(name: str) -> dict[str, Any]:
    return yaml.safe_load((DATA_DIR / name).read_text(encoding="utf-8"))


@lru_cache
def facilities() -> dict[str, Facility]:
    raw = json.loads((DATA_DIR / "facilities.json").read_text(encoding="utf-8"))
    return {f["id"]: Facility(**f) for f in raw}


def facility(fid: str) -> Facility | None:
    return facilities().get(fid)


@lru_cache
def transport_config() -> dict[str, Any]:
    return _yaml("transport_modes.yaml")


@lru_cache
def mode_specs() -> dict[str, dict[str, Any]]:
    return {m["mode"]: m for m in transport_config()["modes"]}


def mode_infos() -> list[TransportModeInfo]:
    return [
        TransportModeInfo(
            mode=TransportMode(m["mode"]),
            label=m["label"],
            speed_kmh=m["speed_kmh"],
            dispatch_min=m["dispatch_min"],
            handover_min=m["handover_min"],
            medic_onboard=m.get("medic_onboard", False),
            enabled=m.get("enabled", True),
            constraints=m.get("constraints", ""),
        )
        for m in transport_config()["modes"]
    ]


@lru_cache
def conditions_config() -> dict[str, Any]:
    return _yaml("conditions.yaml")


@lru_cache
def conditions() -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in conditions_config()["conditions"]}


def condition_infos() -> list[ConditionInfo]:
    return [
        ConditionInfo(
            id=c["id"],
            label=c["label"],
            window_min=c.get("window_min"),
            window_from=c.get("window_from", "onset"),
            window_label=c.get("window_label", ""),
            time_critical=c.get("time_critical", False),
            required_capabilities=c.get("required_capabilities", []),
            high_severity_capabilities=c.get("high_severity_capabilities", []),
            interim_label=(c.get("interim") or {}).get("label"),
        )
        for c in conditions().values()
    ]


@lru_cache
def baseline_config() -> dict[str, Any]:
    return _yaml("baseline.yaml")


@lru_cache
def first_aid() -> dict[str, Any]:
    return _yaml("first_aid.yaml")


@lru_cache
def scenarios() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in sorted((DATA_DIR / "scenarios").glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        out[data["id"]] = data
    return out


def scenario_summaries() -> list[dict[str, Any]]:
    keys = ("id", "title", "story", "proves", "clock", "presenter_notes", "hero", "origin_facility_id")
    items = [{k: s.get(k) for k in keys} for s in scenarios().values()]
    return sorted(items, key=lambda s: (not s.get("hero"), s["id"]))
