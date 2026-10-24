import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile, WebSocket
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.websockets import WebSocketDisconnect

from src import config
from src.services.recordings import RECORDINGS_DIR, save_recording
from src.services.results_log import log_result, read_history
from src.services.rppg_extractor import extract_vitals_from_video
from src.services.sidecar_manager import sidecar_mode
from src.services.transcript_log import log_transcript, read_transcripts
from src.services.transcription import transcribe_pcm, transcribe_stream, transcription_info, wav_bytes
from src.services.video_prep import audio_to_pcm, downsample_video

STATIC = Path(__file__).parent / "static"
RECORDINGS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="AtollCare Part 1 demo")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/recordings", StaticFiles(directory=RECORDINGS_DIR), name="recordings")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"sidecar": sidecar_mode(), "transcription": transcription_info()}


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
