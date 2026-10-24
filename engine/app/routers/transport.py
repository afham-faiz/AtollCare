# F-M4.2 dispatch · F-M4.3 track · F-M4.5 arrive · F-M4.6 asset roster
from uuid import UUID

from fastapi import APIRouter, Depends

from app.models import AssetPatch, Case, DispatchRequest, TrackResponse, TransportAsset
from app.routers.deps import actor_role, hub
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["transport"])


@router.post("/cases/{case_id}/dispatch", response_model=Case)
async def dispatch(case_id: UUID, body: DispatchRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    case = await h.cases.dispatch(case_id, body, "transport" if actor == "clinician" else actor)
    await h.sim.advance(case_id)  # write the first position immediately
    return await h.cases.get(case.id)


@router.get("/cases/{case_id}/track", response_model=TrackResponse)
async def track(case_id: UUID, h: Hub = Depends(hub)):
    return await h.cases.track(case_id)


@router.post("/cases/{case_id}/arrive", response_model=Case)
async def arrive(case_id: UUID, h: Hub = Depends(hub)):
    return await h.cases.arrive(case_id)


@router.get("/transport/assets", response_model=list[TransportAsset])
async def assets(h: Hub = Depends(hub)):
    return await h.world.assets()


@router.patch("/transport/assets/{asset_id}", response_model=TransportAsset)
async def patch_asset(asset_id: str, body: AssetPatch, h: Hub = Depends(hub)):
    return await h.world.patch_asset(asset_id, body)
