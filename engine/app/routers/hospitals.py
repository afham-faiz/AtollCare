# F-M3.8 capacity panel
from fastapi import APIRouter, Depends

from app.models import CapacityPatch, HospitalCapacity
from app.routers.deps import hub
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["hospitals"])


@router.get("/hospitals/capacity", response_model=list[HospitalCapacity])
async def capacity(h: Hub = Depends(hub)):
    return await h.world.capacity()


@router.patch("/hospitals/{facility_id}/capacity", response_model=HospitalCapacity)
async def patch_capacity(facility_id: str, body: CapacityPatch, h: Hub = Depends(hub)):
    return await h.world.patch_capacity(facility_id, body)
