# Network insights (Tiger Data): outcomes and load across every transfer, the storage behind them, and a live
# aggregate-vs-raw benchmark. Seeding demo history is a presenter action.
from fastapi import APIRouter, Depends, Query

from app.models import BenchmarkResponse, InsightsResponse, SeedHistoryResponse
from app.routers.deps import hub
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["insights"])


@router.get("/insights", response_model=InsightsResponse)
async def insights(days: int = Query(30, ge=1, le=120), h: Hub = Depends(hub)):
    return await h.insights.insights(days)


@router.get("/insights/benchmark", response_model=BenchmarkResponse)
async def benchmark(days: int = Query(30, ge=1, le=120), h: Hub = Depends(hub)):
    return await h.insights.benchmark(days)


@router.post("/demo/history", response_model=SeedHistoryResponse)
async def seed_history(days: int = Query(60, ge=7, le=120), per_day: int = Query(8, ge=1, le=40),
                       h: Hub = Depends(hub)):
    return await h.insights.seed(days, per_day)
