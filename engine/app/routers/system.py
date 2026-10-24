# Meta, health, demo controls, Presage bridge heartbeat, TTS and local media.
import mimetypes

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core.clock import real_now
from app.models import (
    BridgeHeartbeat,
    DemoCase,
    DemoState,
    DemoStatePatch,
    HealthResponse,
    MetaResponse,
    OkResponse,
    SpeakRequest,
    SpeakResponse,
    Transfer,
)
from app.routers.deps import hub
from app.services.context import AppError
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/meta", response_model=MetaResponse)
async def meta(h: Hub = Depends(hub)):
    return h.demo.meta()


@router.get("/health", response_model=HealthResponse)
async def health(h: Hub = Depends(hub)):
    ok = await h.svc.repo.ping()
    return HealthResponse(ok=ok, db=f"{h.svc.repo.kind}:{'ok' if ok else 'down'}", adapters=h.svc.adapter_status())


@router.post("/presage/heartbeat", response_model=OkResponse)
async def presage_heartbeat(body: BridgeHeartbeat, h: Hub = Depends(hub)):
    h.svc.bridge = body
    h.svc.bridge_seen = real_now()
    return OkResponse()


@router.post("/voice/speak", response_model=SpeakResponse)
async def speak(body: SpeakRequest, h: Hub = Depends(hub)):
    url = await h.svc.elevenlabs.speak(body.text, body.voice, None)
    return SpeakResponse(audio_url=url, source="elevenlabs" if url else "browser")


@router.get("/demo/state", response_model=DemoState)
async def demo_state(h: Hub = Depends(hub)):
    return h.svc.clock.state


@router.patch("/demo/state", response_model=DemoState)
async def patch_demo_state(body: DemoStatePatch, h: Hub = Depends(hub)):
    return await h.demo.patch(body)


@router.post("/demo/reset", response_model=OkResponse)
async def reset(h: Hub = Depends(hub)):
    await h.demo.reset()
    return OkResponse()


@router.get("/demo/cases", response_model=list[DemoCase])
async def demo_cases(h: Hub = Depends(hub)):
    return h.transfers.demo_cases()


@router.post("/demo/cases/{case_id}", response_model=Transfer)
async def start_case(case_id: str, h: Hub = Depends(hub)):
    return await h.transfers.start_case(case_id)


@router.post("/demo/example", response_model=Transfer)
async def example(h: Hub = Depends(hub)):
    """First prepared case of the active region."""
    return await h.transfers.start_case()


@router.get("/media/{key:path}")
async def media(key: str, h: Hub = Depends(hub)):
    if h.svc.storage.mode != "local":
        raise AppError("not_local", "Media is served from object storage", 404)
    try:
        path = h.svc.storage.local_path(key)
    except ValueError as exc:
        raise AppError("bad_key", "Invalid media key", 400) from exc
    if not path.exists():
        raise AppError("not_found", "Media not found", 404)
    return FileResponse(path, media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream")
