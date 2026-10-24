# F-M8.1 reset · F-M8.2 world controls · F-M8.3 scenarios
from fastapi import APIRouter, Depends, Query

from app.models import Case, DemoState, DemoStatePatch, OkResponse
from app.routers.deps import hub
from app.services.hub import Hub

router = APIRouter(prefix="/api/demo", tags=["demo"])


@router.get("/state", response_model=DemoState)
async def get_state(h: Hub = Depends(hub)):
    return h.world.state()


@router.patch("/state", response_model=DemoState)
async def patch_state(body: DemoStatePatch, h: Hub = Depends(hub)):
    return await h.world.patch(body)


@router.post("/reset", response_model=OkResponse)
async def reset(h: Hub = Depends(hub)):
    await h.world.reset()
    return OkResponse()


@router.post("/scenario/{scenario_id}", response_model=Case)
async def scenario(scenario_id: str, autoplay: bool = Query(False), h: Hub = Depends(hub)):
    return await h.scenarios.load(scenario_id, autoplay)
