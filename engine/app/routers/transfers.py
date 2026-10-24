# Transfers API — crew screen, hospital screen and the Presage bridge all talk to these endpoints.
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile

from app.models import (
    AcceptRequest,
    CreateTransferRequest,
    MessageRequest,
    MonitoringRequest,
    NoteRequest,
    Transfer,
    TransferListItem,
    TrendResponse,
    VitalsAck,
    VitalsRequest,
)
from app.routers.deps import hub
from app.services.context import AppError
from app.services.hub import Hub

router = APIRouter(prefix="/api/transfers", tags=["transfers"])


@router.get("", response_model=list[TransferListItem])
async def list_transfers(status: str | None = None, h: Hub = Depends(hub)):
    return await h.transfers.list(status)


@router.post("", response_model=Transfer)
async def create_transfer(body: CreateTransferRequest, h: Hub = Depends(hub)):
    return await h.transfers.create(body)


@router.get("/{transfer_id}", response_model=Transfer)
async def get_transfer(transfer_id: UUID, h: Hub = Depends(hub)):
    return await h.transfers.get(transfer_id)


@router.post("/{transfer_id}/vitals", response_model=VitalsAck)
async def add_vitals(transfer_id: UUID, body: VitalsRequest, h: Hub = Depends(hub)):
    return await h.transfers.add_vitals(transfer_id, body)


@router.get("/{transfer_id}/vitals/trend", response_model=TrendResponse)
async def trend(transfer_id: UUID, window_min: int = Query(60, ge=5, le=720), h: Hub = Depends(hub)):
    return await h.transfers.trend(transfer_id, window_min)


@router.post("/{transfer_id}/monitoring", response_model=Transfer)
async def monitoring(transfer_id: UUID, body: MonitoringRequest, h: Hub = Depends(hub)):
    return await h.transfers.set_monitoring(transfer_id, body.source)


@router.post("/{transfer_id}/notes", response_model=Transfer)
async def add_note(transfer_id: UUID, body: NoteRequest, h: Hub = Depends(hub)):
    return await h.transfers.add_note(transfer_id, body)


@router.post("/{transfer_id}/notes/voice", response_model=Transfer)
async def voice_note(
    transfer_id: UUID,
    audio: UploadFile = File(...),
    reply_to: UUID | None = Form(None),
    h: Hub = Depends(hub),
):
    data = await audio.read()
    if not data:
        raise AppError("empty_audio", "No audio received", 422)
    return await h.transfers.voice_note(transfer_id, data, audio.filename or "note.webm",
                                        audio.content_type or "audio/webm", reply_to)


@router.post("/{transfer_id}/messages", response_model=Transfer)
async def message(transfer_id: UUID, body: MessageRequest, h: Hub = Depends(hub)):
    return await h.transfers.message(transfer_id, body)


@router.post("/{transfer_id}/handoff", response_model=Transfer)
async def handoff(transfer_id: UUID, h: Hub = Depends(hub)):
    return await h.transfers.handoff(transfer_id)


@router.post("/{transfer_id}/accept", response_model=Transfer)
async def accept(transfer_id: UUID, body: AcceptRequest, h: Hub = Depends(hub)):
    return await h.transfers.accept(transfer_id, body)


@router.post("/{transfer_id}/arrive", response_model=Transfer)
async def arrive(transfer_id: UUID, h: Hub = Depends(hub)):
    return await h.transfers.arrive(transfer_id)


@router.post("/{transfer_id}/close", response_model=Transfer)
async def close(transfer_id: UUID, h: Hub = Depends(hub)):
    return await h.transfers.close(transfer_id)
