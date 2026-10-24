import asyncio
import base64
import time
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from src import config
from pydantic import BaseModel

from src.models.schemas import Demographics, PreArrivalPacket, RppgEstimates, VisualCueReport
from src.services import engine_client
from src.services.account_digest import digest_account
from src.services.cue_log import log_visual_cues, read_visual_cues
from src.services.handshake_log import log_handshake, read_handshakes
from src.services.packet import build_packet
from src.services.id_log import log_id_scan, read_id_scans
from src.services.ocr_service import parse_identity_doc
from src.services.recordings import RECORDINGS_DIR, save_recording
from src.services.results_log import log_result, read_history
from src.services.rppg_extractor import extract_vitals_from_video
from src.services.sidecar_manager import sidecar_mode
from src.services.transcript_log import log_transcript, read_transcripts
from src.services.transcription import transcribe_pcm, transcribe_stream, transcription_info, wav_bytes
from src.services.video_analysis import analyse_video
from src.services.video_prep import audio_to_pcm, downsample_video
from src.services.vqa_evaluator import run_visual_cue_session

STATIC = Path(__file__).parent / "static"
RECORDINGS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AtollCare Part 1 demo")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/recordings", StaticFiles(directory=RECORDINGS_DIR), name="recordings")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


def video_record_settings() -> dict:
    """What the page needs to record video. A missing setting is reported, never raised."""
    try:
        return {"max_s": config.VIDEO_RECORD_MAX_S, "error": None}
    except config.ConfigError as exc:
        return {"max_s": None, "error": str(exc)}


@app.get("/api/health")
def health() -> dict:
    return {"sidecar": sidecar_mode(), "transcription": transcription_info(), "video_record": video_record_settings()}


@app.post("/api/vitals")
def vitals(video: UploadFile = File(...)) -> dict:
    """Downsample the upload, run it through Presage, return estimates plus timings."""
    raw = video.file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    if sidecar_mode() is None:
        raise HTTPException(503, "Presage sidecar is not running. Start the app with: python run.py --serve")

    t0 = time.time()
    small = downsample_video(raw)
    t1 = time.time()
    video_file = save_recording("video", small, "mp4", label=video.filename or "")  # keep every trial
    estimates = extract_vitals_from_video(small)
    t2 = time.time()
    sizes = {"original": round(len(raw) / 1e6, 1), "sent": round(len(small) / 1e6, 1)}
    seconds = {"downsample": round(t1 - t0, 1), "presage": round(t2 - t1, 1)}
    log_result(video.filename or "upload", sizes, seconds, estimates, saved_file=video_file)
    return {"result": estimates.model_dump(), "sidecar_mode": sidecar_mode(), "sizes_mb": sizes, "seconds": seconds,
            "video_file": video_file}


@app.get("/api/history")
def history() -> list[dict]:
    return read_history()


@app.get("/api/transcripts")
def transcripts() -> list[dict]:
    return read_transcripts()


@app.post("/api/transcribe-file")
def transcribe_file(audio: UploadFile = File(...)) -> dict:
    """Transcribe an uploaded audio (or video) file in one go. Every attempt is saved and logged."""
    raw = audio.file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    try:
        pcm = audio_to_pcm(raw)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    audio_file = save_recording("upload", wav_bytes(pcm), "wav", label=audio.filename or "")
    entry = {"source": "file", "filename": audio.filename, "audio_file": audio_file}
    try:
        result = transcribe_pcm(pcm)
    except Exception as exc:
        log_transcript({**entry, "error": f"{exc.__class__.__name__}: {exc}", "transcript": "", "segments": [],
                        "duration_s": round(len(pcm) / 32000, 1)})
        raise HTTPException(502, f"{exc.__class__.__name__}: {exc}") from exc
    result = {**result, **entry}
    log_transcript(result)
    return result


@app.post("/api/analyse-video")
def analyse(video: UploadFile = File(...), transcript: str = Form(""), age: str = Form(""),
            presage: str = Form("true")) -> dict:
    """The one video entry point: visual signs (Gemini) plus, if switched on, heart/breathing rate (Presage)."""
    raw = video.file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    use_presage = presage.strip().lower() in ("1", "true", "yes", "on")
    name = video.filename or "upload"
    try:
        result = analyse_video(raw, transcript, int(age) if age.strip().isdigit() else None, use_presage)
    except config.ConfigError as exc:  # e.g. VQA_MODE missing from inputs/.env
        raise HTTPException(500, str(exc)) from exc

    video_file = save_recording("video", result.small, "mp4", label=name)  # keep every trial
    if result.estimates is not None:
        log_result(name, result.sizes_mb, {"downsample": result.seconds["downsample"], "presage": result.seconds["presage"]},
                   result.estimates, saved_file=video_file)

    cited = {i for f in result.report.findings for i in f.evidence_frames}
    evidence: dict[str, dict] = {}
    files: dict[int, str | None] = {}
    for fr in result.frames:
        if fr.index in cited:  # keep only the frames a conclusion depends on
            files[fr.index] = save_recording("cue-frame", fr.jpeg, "jpg", label=f"{name}_f{fr.index}")
            evidence[str(fr.index)] = {"t_s": fr.t_s, "file": files[fr.index],
                                       "data_url": "data:image/jpeg;base64," + base64.b64encode(fr.jpeg).decode()}
    log_visual_cues(name, transcript, result.report, files)
    return {
        "vitals": result.estimates.model_dump() if result.estimates else None,
        "vitals_note": result.vitals_note,
        "signs": {"report": result.report.model_dump(), "evidence": evidence},
        "used_account": bool(transcript.strip()),
        "video_file": video_file,
        "sizes_mb": result.sizes_mb,
        "seconds": result.seconds,
    }


@app.post("/api/visual-cues")
def visual_cues(video: UploadFile = File(...), transcript: str = Form(""), age: str = Form("")) -> dict:
    """Plan which cues to look for from the account, then inspect the video for them. Never fails on a bad read."""
    raw = video.file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    report, frames = run_visual_cue_session(raw, transcript, int(age) if age.strip().isdigit() else None)

    cited = {i for f in report.findings for i in f.evidence_frames}
    evidence: dict[str, dict] = {}
    files: dict[int, str | None] = {}
    for fr in frames:
        if fr.index in cited:  # keep only the frames a conclusion depends on
            files[fr.index] = save_recording("cue-frame", fr.jpeg, "jpg", label=f"{video.filename or 'video'}_f{fr.index}")
            evidence[str(fr.index)] = {"t_s": fr.t_s, "file": files[fr.index],
                                       "data_url": "data:image/jpeg;base64," + base64.b64encode(fr.jpeg).decode()}
    log_visual_cues(video.filename or "upload", transcript, report, files)
    return {"report": report.model_dump(), "evidence": evidence}


@app.get("/api/visual-cue-sessions")
def visual_cue_sessions() -> list[dict]:
    return read_visual_cues()


@app.post("/api/scan-id")
def scan_id(image: UploadFile = File(...)) -> dict:
    """Read name, ID number and age from a photo of an ID. Never fails on a bad read: see `issues`."""
    raw = image.file.read()
    if not raw:
        raise HTTPException(400, "Empty upload")
    result = parse_identity_doc(raw)
    ext = (Path(image.filename or "").suffix.lstrip(".") or "jpg").lower()
    image_file = save_recording("id", raw, ext, label=image.filename or "")  # keep every trial
    log_id_scan(image.filename or "upload", result, saved_file=image_file)
    return {"result": result.model_dump(), "image_file": image_file}


@app.get("/api/id-scans")
def id_scans() -> list[dict]:
    return read_id_scans()


class PreviewRequest(BaseModel):
    """What the page already holds from the three boxes. Every part is optional."""

    demographics: Demographics | None = None
    account: str = ""
    vitals: RppgEstimates | None = None
    signs: VisualCueReport | None = None


class SendRequest(BaseModel):
    packet: PreArrivalPacket   # exactly the packet that was previewed
    origin_id: str
    destination_id: str
    mode: str


@app.get("/api/handshake/options")
def handshake_options() -> dict:
    """Facilities and transport modes offered by the crew app, for the From, To and Mode pickers."""
    return engine_client.get_options()


@app.post("/api/handshake/preview")
def handshake_preview(req: PreviewRequest) -> dict:
    """Build the packet that would be sent, with what is withheld and what is missing. Sends nothing."""
    try:
        digest = digest_account(req.account)
        packet = build_packet(demographics=req.demographics, vitals=req.vitals, signs=req.signs, digest=digest)
    except config.ConfigError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"packet": packet.model_dump(), "account_checked": digest.redacted}


@app.post("/api/handshake/send")
def handshake_send(req: SendRequest) -> dict:
    """Create the transfer in the crew app and fill it in. Starts their journey clock, so only call on departure."""
    try:
        result = engine_client.send_packet(req.packet, req.origin_id, req.destination_id, req.mode)
    except config.ConfigError as exc:
        raise HTTPException(500, str(exc)) from exc
    log_handshake(req.packet, {"origin_id": req.origin_id, "destination_id": req.destination_id, "mode": req.mode}, result)
    return result.model_dump()


@app.get("/api/handshakes")
def handshakes() -> list[dict]:
    return read_handshakes()


@app.websocket("/ws/transcribe")
async def ws_transcribe(ws: WebSocket) -> None:
    """Browser streams 16 kHz PCM16 mono as binary frames; sends the text 'end' when finished.

    Replies with JSON: ready, interim, final, notice, done (with the full transcript) or error.
    """
    await ws.accept()
    audio_q: asyncio.Queue[bytes | None] = asyncio.Queue()
    pcm_all = bytearray()  # kept so every trial can be saved and replayed

    async def send(event: dict) -> None:
        try:
            await ws.send_json(event)
        except (RuntimeError, WebSocketDisconnect):
            pass  # browser already gone

    info = transcription_info()
    await send({"type": "ready", **info})
    if info["mode"] == "error":
        await send({"type": "error", "message": info["error"]})
        await ws.close()
        return

    task = asyncio.create_task(transcribe_stream(audio_q, send))
    try:
        while not task.done():
            try:
                msg = await asyncio.wait_for(ws.receive(), timeout=0.5)
            except asyncio.TimeoutError:
                continue
            if msg["type"] == "websocket.disconnect":
                break
            if msg.get("bytes"):
                pcm_all += msg["bytes"]
                audio_q.put_nowait(msg["bytes"])
            elif msg.get("text") == "end":
                break
    finally:
        audio_q.put_nowait(None)

    audio_file = save_recording("voice", wav_bytes(bytes(pcm_all)), "wav") if pcm_all else None
    entry = {"source": "microphone", "audio_file": audio_file}
    try:
        result = await task
    except Exception as exc:  # bad key, network, model name, etc.
        message = f"{exc.__class__.__name__}: {exc}"
        if pcm_all:  # a failed attempt is still a trial worth keeping
            log_transcript({**entry, "error": message, "transcript": "", "segments": [],
                            "duration_s": round(len(pcm_all) / 32000, 1)})
        await send({"type": "error", "message": message})
    else:
        result = {**result, **entry}
        if result["duration_s"] > 0:
            log_transcript(result)
        await send({"type": "done", **result})
    try:
        await ws.close()
    except RuntimeError:
        pass
