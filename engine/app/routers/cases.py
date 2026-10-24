# F-M1.1 create · F-M1.3 patch · F-M1.5 submit · F-M1.6 refer · F-M3.1 list · F-M3.3/3.4 respond/info ·
# F-M3.6 notes · F-M3.7 close · F-M5.3 guidance · F-M2.7 SBAR preview
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.models import (
    Case,
    CaseListItem,
    CloseRequest,
    CreateCaseRequest,
    GuidanceResponse,
    InfoAnswersRequest,
    IntakeRequest,
    NoteRequest,
    PatchCaseRequest,
    ReferRequest,
    RespondRequest,
    SbarSummary,
)
from app.routers.deps import actor_role, hub
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["cases"])


@router.get("/cases", response_model=list[CaseListItem])
async def list_cases(
    status: str | None = None, destination_id: str | None = None, origin_id: str | None = None, h: Hub = Depends(hub)
):
    return await h.cases.list(status, destination_id, origin_id)


@router.post("/cases", response_model=Case)
async def create_case(body: CreateCaseRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.create(body, actor=actor if actor != "clinician" else "reporter")


@router.get("/cases/{case_id}", response_model=Case)
async def get_case(case_id: UUID, h: Hub = Depends(hub)):
    return await h.cases.get(case_id)


@router.patch("/cases/{case_id}", response_model=Case)
async def patch_case(case_id: UUID, body: PatchCaseRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.patch(case_id, body, actor)


@router.post("/cases/{case_id}/submit", response_model=Case)
async def submit_case(case_id: UUID, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.submit(case_id, actor)


@router.post("/cases/{case_id}/intake", response_model=Case)
async def intake(case_id: UUID, body: IntakeRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.intake(case_id, body.raw_text, body.language, actor)


@router.post("/cases/{case_id}/refer", response_model=Case)
async def refer(case_id: UUID, body: ReferRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.refer(case_id, body, actor)


@router.get("/cases/{case_id}/sbar", response_model=SbarSummary)
async def sbar_preview(case_id: UUID, h: Hub = Depends(hub)):
    return await h.cases.sbar_preview(case_id)


@router.post("/cases/{case_id}/referral/respond", response_model=Case)
async def respond(case_id: UUID, body: RespondRequest, h: Hub = Depends(hub)):
    return await h.cases.respond(case_id, body)


@router.post("/cases/{case_id}/referral/info", response_model=Case)
async def referral_info(case_id: UUID, body: InfoAnswersRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.provide_info(case_id, body, actor)


@router.post("/cases/{case_id}/close", response_model=Case)
async def close(case_id: UUID, body: CloseRequest, h: Hub = Depends(hub), actor: str = Depends(actor_role)):
    return await h.cases.close(case_id, body, actor)


@router.post("/cases/{case_id}/notes", response_model=Case)
async def notes(case_id: UUID, body: NoteRequest, h: Hub = Depends(hub)):
    return await h.cases.add_note(case_id, body.text, body.actor_role)


@router.get("/cases/{case_id}/guidance", response_model=GuidanceResponse)
async def guidance(case_id: UUID, role: str = Query("reporter"), h: Hub = Depends(hub)):
    return await h.cases.guidance(case_id, role)
