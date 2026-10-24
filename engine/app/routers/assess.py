# F-M2.1 re-run engine · F-M2.5 all routes (incl. infeasible with reasons) · F-M2.6 vitals trend + forecast
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core import forecast as forecast_mod
from app.core import summary
from app.models import Case, RouteOption, TrendResponse
from app.routers.deps import actor_role, hub
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["engine"])


@router.post("/cases/{case_id}/assess", response_model=Case)
async def assess(case_id: UUID, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.assess(case_id, actor)


@router.get("/cases/{case_id}/routes", response_model=list[RouteOption])
async def routes(case_id: UUID, h: Hub = Depends(hub)):
    case = await h.cases.get(case_id)
    if case.intake is None and not case.vitals and case.recommendation is None:
        return []
    return await h.cases.compute_routes(case)


@router.get("/cases/{case_id}/vitals/trend", response_model=TrendResponse)
async def trend(case_id: UUID, window_min: int = Query(60, ge=5, le=24 * 60), h: Hub = Depends(hub)):
    case = await h.cases.get(case_id)
    res = await h.cases.trend(case_id, window_min)
    route = summary.chosen_route(case)
    arrive = case.transport.eta or (route.arrive_at if route else None)
    res.forecast = forecast_mod.forecast(res.buckets, h.cases.now(), arrive)
    return res
