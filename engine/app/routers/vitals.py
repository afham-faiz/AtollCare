# F-M6.3 manual vitals · F-M6.1 camera scan upload · F-M6.2 scan job status
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile

from app.models import Case, ManualVitalsRequest, ScanJobCreated, ScanJobStatus
from app.routers.deps import actor_role, hub
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["vitals"])


@router.post("/cases/{case_id}/vitals", response_model=Case)
async def add_vitals(case_id: UUID, body: ManualVitalsRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.add_vitals(case_id, body, actor)


@router.post("/cases/{case_id}/vitals/scan", response_model=ScanJobCreated)
async def scan(case_id: UUID, video: UploadFile = File(...), h: Hub = Depends(hub)):
    data = await video.read()
    job_id = await h.scans.start(case_id, data, video.content_type or "video/webm")
    return ScanJobCreated(job_id=job_id)


@router.get("/vitals/scan/{job_id}", response_model=ScanJobStatus)
async def scan_status(job_id: str, h: Hub = Depends(hub)):
    return h.scans.status(job_id)
