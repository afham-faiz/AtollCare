# Pre-arrival packets: the companion's phone builds one (clip, account, ID), sends it, and the crew starts a transfer
# from it. Uploads are multipart; everything else is JSON.
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.models import CreateIntakeRequest, Intake, StartTransferRequest, Transfer, UpdateIntakeRequest
from app.routers.deps import hub
from app.services.context import AppError
from app.services.hub import Hub

router = APIRouter(prefix="/api/intakes", tags=["intakes"])


@router.post("", response_model=Intake)
async def create_intake(body: CreateIntakeRequest, h: Hub = Depends(hub)):
    return await h.intakes.create(body)


@router.get("", response_model=list[Intake])
async def list_intakes(status: str | None = None, h: Hub = Depends(hub)):
    return await h.intakes.list(status)


@router.get("/{intake_id}", response_model=Intake)
async def get_intake(intake_id: UUID, h: Hub = Depends(hub)):
    return await h.intakes.get(intake_id)


@router.patch("/{intake_id}", response_model=Intake)
async def update_intake(intake_id: UUID, body: UpdateIntakeRequest, h: Hub = Depends(hub)):
    return await h.intakes.update(intake_id, body)


def presage_result(raw: str | None) -> dict | None:
    """The live Presage summary the phone sends with its clip (JSON), if it streamed to the bridge."""
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise AppError("bad_presage_result", "The live Presage result isn't valid JSON", 422) from exc
    if not isinstance(data, dict):
        raise AppError("bad_presage_result", "The live Presage result should be an object", 422)
    return data


@router.post("/{intake_id}/scans", response_model=Intake)
async def add_scan(intake_id: UUID, video: UploadFile = File(...), presage: str | None = Form(None),
                   h: Hub = Depends(hub)):
    """A clip from the companion's phone. `presage`: the bridge's live summary when the phone streamed while
    recording; otherwise Presage measures the clip itself."""
    return await h.intakes.add_scan(intake_id, await video.read(), presage_result(presage))


@router.post("/{intake_id}/account/voice", response_model=Intake)
async def account_voice(intake_id: UUID, audio: UploadFile = File(...), h: Hub = Depends(hub)):
    data = await audio.read()
    return await h.intakes.account_voice(intake_id, data, audio.filename or "account.webm",
                                         audio.content_type or "audio/webm")


@router.post("/{intake_id}/id-photo", response_model=Intake)
async def id_photo(intake_id: UUID, image: UploadFile = File(...), h: Hub = Depends(hub)):
    return await h.intakes.id_photo(intake_id, await image.read())


@router.post("/{intake_id}/send", response_model=Intake)
async def send(intake_id: UUID, h: Hub = Depends(hub)):
    return await h.intakes.send(intake_id)


@router.post("/{intake_id}/transfer", response_model=Transfer)
async def start_transfer(intake_id: UUID, body: StartTransferRequest, h: Hub = Depends(hub)):
    return await h.intakes.start_transfer(intake_id, body)
