# F-M5.1 speech-to-text · F-M5.2 text-to-speech · F-M1.8 spoken status · F-M4.8 crew brief
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.core import refdata, summary
from app.models import CrewBriefResponse, SpeakRequest, SpeakResponse, TranscribeResponse
from app.routers.deps import hub
from app.services.context import AppError
from app.services.hub import Hub

router = APIRouter(prefix="/api", tags=["voice"])
DEFAULT_MOCK_TEXT = refdata.scenarios()["laamu_stemi_night"]["intake_text"]


@router.post("/voice/transcribe", response_model=TranscribeResponse)
async def transcribe(
    audio: UploadFile = File(...),
    language: str | None = Form(None),
    case_id: UUID | None = Form(None),
    h: Hub = Depends(hub),
):
    data = await audio.read()
    if not data:
        raise AppError("empty_audio", "No audio received", 422)
    mock_text = DEFAULT_MOCK_TEXT
    if case_id is not None:
        case = await h.cases.get(case_id)
        sc = refdata.scenarios().get(case.meta.scenario_id or "")
        if sc:
            mock_text = sc["intake_text"]
    try:
        text, lang, conf, source = await h.svc.elevenlabs.transcribe(
            data, audio.filename or "voice.webm", audio.content_type or "audio/webm", language, mock_text
        )
    except Exception as exc:  # noqa: BLE001
        raise AppError("stt_failed", f"Transcription failed ({type(exc).__name__}) — please type instead", 502) from exc
    return TranscribeResponse(text=text, language=lang, confidence=conf, source=source)  # type: ignore[arg-type]


@router.post("/voice/speak", response_model=SpeakResponse)
async def speak(body: SpeakRequest, h: Hub = Depends(hub)):
    if not body.text.strip():
        raise AppError("empty_text", "Nothing to speak", 422)
    url = await h.svc.elevenlabs.speak(body.text[:1500], body.voice, body.language)
    return SpeakResponse(audio_url=url, source="elevenlabs" if url else "browser")


@router.get("/cases/{case_id}/status-sentence", response_model=CrewBriefResponse)
async def status_sentence(case_id: UUID, speak: bool = False, h: Hub = Depends(hub)):
    case = await h.cases.get(case_id)
    text = summary.status_sentence(case, h.cases.now())
    url = await h.svc.elevenlabs.speak(text, "status", case.meta.language) if speak else None
    return CrewBriefResponse(text=text, audio_url=url)


@router.get("/cases/{case_id}/crew-brief", response_model=CrewBriefResponse)
async def crew_brief(case_id: UUID, speak: bool = False, h: Hub = Depends(hub)):
    case = await h.cases.get(case_id)
    text = summary.crew_brief(case)
    url = await h.svc.elevenlabs.speak(text, "status", None) if speak else None
    return CrewBriefResponse(text=text, audio_url=url)
