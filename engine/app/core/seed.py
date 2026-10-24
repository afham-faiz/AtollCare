# F-M8.1 Seed data for transport assets & hospital capacity (§11). DEMO ASSUMPTION.
from __future__ import annotations

from datetime import datetime

from app.core import refdata
from app.models import HospitalCapacity, TransportAsset, TransportMode

HOSPITAL_TYPES = {"tertiary_hospital", "regional_hospital", "atoll_hospital"}


def seed_assets() -> list[TransportAsset]:
    """1 sea ambulance + 1 speedboat per hospital; 2 seaplanes + 1 fixed-wing (+1 helicopter, mode disabled by
    default) at Hulhulé; 1 speedboat per health centre."""
    assets: list[TransportAsset] = []
    for fac in refdata.facilities().values():
        if fac.type in HOSPITAL_TYPES:
            assets.append(TransportAsset(id=f"sa_{fac.id}", mode=TransportMode.sea_ambulance,
                                         home_facility_id=fac.id, status="available", crew_note="Medic + 2 crew"))
            assets.append(TransportAsset(id=f"sb_{fac.id}", mode=TransportMode.speedboat,
                                         home_facility_id=fac.id, status="available", crew_note="2 crew"))
        if fac.type == "health_centre":
            assets.append(TransportAsset(id=f"sb_{fac.id}", mode=TransportMode.speedboat,
                                         home_facility_id=fac.id, status="available", crew_note="Island ferry crew"))
    assets += [
        TransportAsset(id="sp_hulhule_1", mode=TransportMode.seaplane, home_facility_id="hulhule", status="available",
                       crew_note="Twin Otter, stretcher fit"),
        TransportAsset(id="sp_hulhule_2", mode=TransportMode.seaplane, home_facility_id="hulhule", status="available",
                       crew_note="Twin Otter, stretcher fit"),
        TransportAsset(id="fw_hulhule_1", mode=TransportMode.fixed_wing, home_facility_id="hulhule", status="available",
                       crew_note="Medevac Dash 8, flight nurse"),
        TransportAsset(id="heli_hulhule_1", mode=TransportMode.helicopter, home_facility_id="hulhule",
                       status="available", crew_note="Hypothetical — mode disabled unless toggled in /demo"),
    ]
    return assets


def seed_capacity(now: datetime) -> list[HospitalCapacity]:
    out: list[HospitalCapacity] = []
    for fac in refdata.facilities().values():
        if fac.type not in HOSPITAL_TYPES:
            continue
        caps = set(fac.capabilities)
        out.append(
            HospitalCapacity(
                facility_id=fac.id,
                icu_beds_free=(4 if fac.id == "igmh" else 2) if "icu" in caps else None,
                cath_lab_available=True if "cath_lab" in caps else None,
                ct_available=True if "ct" in caps else None,
                blood_bank_units=(40 if fac.id == "igmh" else 12) if "blood_bank" in caps else None,
                updated_at=now,
            )
        )
    return out
