# F-M7.5 meta + health · F-M7.4 local media
import mimetypes

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.core import refdata
from app.models import HealthResponse, MetaResponse
from app.routers.deps import hub
from app.services.context import AppError
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["meta"])

# F-M5.4 language selector. Voice support for Dhivehi is NOT claimed until verified with ElevenLabs.
LANGUAGES = [
    {"code": "en", "label": "English", "voice": True},
    {"code": "dv", "label": "Dhivehi (ދިވެހި)", "voice": False, "note": "Voice not yet available — text only"},
    {"code": "hi", "label": "Hindi", "voice": True},
    {"code": "ta", "label": "Tamil", "voice": True},
    {"code": "bn", "label": "Bengali", "voice": False, "note": "Voice support unverified — text only"},
]


@router.get("/meta", response_model=MetaResponse)
async def meta(h: Hub = Depends(hub)):
    return MetaResponse(
        facilities=list(refdata.facilities().values()),
        transport_modes=[
            m.model_copy(update={"enabled": h.world.state().helicopter_enabled}) if m.mode.value == "helicopter" else m
            for m in refdata.mode_infos()
        ],
        conditions=refdata.condition_infos(),
        adapters=h.svc.adapter_status(),
        demo_state=h.world.state(),
        now=h.svc.clock.now(),
        clock=h.world.clock_info(),
        languages=LANGUAGES,
        scenarios=refdata.scenario_summaries(),
    )


@router.get("/health", response_model=HealthResponse)
async def health(h: Hub = Depends(hub)):
    ok = await h.svc.repo.ping()
    return HealthResponse(ok=ok, db=f"{h.svc.repo.kind}:{'ok' if ok else 'down'}", adapters=h.svc.adapter_status())


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
