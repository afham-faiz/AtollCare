"""Speech transcription for the companion's voice.

Live microphone: audio arrives as 16 kHz mono 16-bit PCM chunks on an asyncio.Queue (None = finished)
and events are reported through an async callback:
    {"type": "interim", "text": ...}   partial text, replaced as the speaker continues
    {"type": "final",   "text": ...}   one finished utterance
    {"type": "notice",  "text": ...}   something the user should know (e.g. the backup model took over)

The model comes from inputs/.env (GEMINI_STT_MODEL); the method is chosen from its name:
    name contains "live"  -> streaming over the Gemini Live API
    anything else         -> chunked: each sentence goes to generateContent after a pause
GEMINI_STT_FALLBACK_MODEL is used if the main model cannot start. No GEMINI_API_KEY -> mock.

Audio files: transcribe_pcm() sends a whole recording in one request (split only if very long).
"""
import array
import asyncio
import io
import math
import time
import wave
from collections.abc import Awaitable, Callable

from src import config
from src.services.gemini_client import make_client

SAMPLE_RATE = 16000
BYTES_PER_SECOND = SAMPLE_RATE * 2  # 16-bit mono
FINAL_GRACE_S = 4.0       # live: how long to wait for the last text after the speaker stops
IDLE_FLUSH_S = 1.5        # live: text with no new fragments for this long counts as finished
SPEECH_RMS = 0.015        # flash: chunk loudness (0-1) that counts as speech
FILE_PIECE_S = 240        # files longer than this are sent in pieces of this length

SILENT_TRANSCRIBER = (
    "You are a silent transcription service. Never speak, answer or comment. "
    "Do not produce any response to what you hear."
)
NO_SPEECH = "NO_SPEECH"
FLASH_PROMPT = (
    "Transcribe the human speech in this audio verbatim{lang}. Output only the transcript text, nothing else. "
    "Never invent or guess words. If the audio contains no clearly intelligible human speech "
    "(silence, noise, a tone, music, breathing, a few unclear sounds), output exactly " + NO_SPEECH + "."
)

OnEvent = Callable[[dict], Awaitable[None]]


def stt_method(model: str | None = None) -> str:
    """'mock', 'live' or 'flash' for a model name (default: the main speech model)."""
    if not config.GEMINI_API_KEY:
        return "mock"
    return "live" if "live" in (model or config.GEMINI_STT_MODEL).lower() else "flash"


def transcription_info() -> dict:
    """What the page shows. Never raises: a missing setting is reported as mode 'error'."""
    try:
        method = stt_method()
        return {
            "mode": "mock" if method == "mock" else "gemini",
            "method": method,
            "model": config.GEMINI_STT_MODEL if method != "mock" else None,
            "fallback_model": config.GEMINI_STT_FALLBACK_MODEL or None,
            "silence_stop_s": config.STT_SILENCE_STOP_S,
        }
    except config.ConfigError as exc:
        return {"mode": "error", "error": str(exc), "silence_stop_s": 2.0}


class _CountingQueue:
    """Wraps the audio queue so we know whether the main model consumed any audio before failing."""

    def __init__(self, q: "asyncio.Queue[bytes | None]"):
        self._q = q
        self.taken = 0

    async def get(self):
        item = await self._q.get()
        self.taken += 1
        return item


async def transcribe_stream(audio_q: "asyncio.Queue[bytes | None]", on_event: OnEvent) -> dict:
    """Run one transcription session. Returns {mode, model, transcript, segments, duration_s}."""
    primary = config.GEMINI_STT_MODEL
    counted = _CountingQueue(audio_q)
    try:
        result = await _run(stt_method(primary), primary, counted, on_event)
        used, fallback_from = primary, None
    except Exception as exc:
        backup = config.GEMINI_STT_FALLBACK_MODEL
        # Only switch if nothing was read yet, otherwise audio would be lost.
        if not backup or backup == primary or counted.taken:
            raise
        await on_event({"type": "notice",
                        "text": f"{primary} could not start ({exc.__class__.__name__}); using backup model {backup}."})
        result = await _run(stt_method(backup), backup, counted, on_event)
        used, fallback_from = backup, primary
    mode = "mock" if stt_method(used) == "mock" else "gemini"
    return {"mode": mode, "model": None if mode == "mock" else used, "fallback_from": fallback_from, **result}


async def _run(method: str, model: str, audio_q, on_event: OnEvent) -> dict:
    runner = {"live": _live_session, "flash": _flash_session}.get(method, _mock_session)
    return await runner(audio_q, on_event, model)


def _rms(chunk: bytes) -> float:
    samples = array.array("h")
    samples.frombytes(chunk[: len(chunk) // 2 * 2])
    if not samples:
        return 0.0
    return math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768


def wav_bytes(pcm: bytes) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(pcm)
    return buf.getvalue()


# ---------------------------------------------------------------- mock

async def _mock_session(audio_q, on_event: OnEvent, model: str) -> dict:
    received = 0
    last_report = 0.0
    while (chunk := await audio_q.get()) is not None:
        received += len(chunk)
        seconds = received / BYTES_PER_SECOND
        if seconds - last_report >= 1.0:
            last_report = seconds
            await on_event({"type": "interim", "text": f"(mock) hearing audio… {seconds:.0f}s"})
    if not received:
        return {"transcript": "", "segments": [], "duration_s": 0.0}
    seconds = received / BYTES_PER_SECOND
    text = f"(mock transcript) received {seconds:.1f}s of audio. Add GEMINI_API_KEY to inputs/.env for real text."
    await on_event({"type": "final", "text": text})
    return {"transcript": text, "segments": [text], "duration_s": round(seconds, 1)}


# ---------------------------------------------------------------- live (streaming)

async def _live_session(audio_q, on_event: OnEvent, model: str) -> dict:
    from google.genai import types

    client = make_client()
    transcription_cfg = types.AudioTranscriptionConfig()
    if "transcribe" in model and config.TRANSCRIBE_LANGUAGE:
        transcription_cfg = types.AudioTranscriptionConfig(language_codes=[config.TRANSCRIBE_LANGUAGE])
    live_config = types.LiveConnectConfig(
        # Native-audio Live models only accept AUDIO output; we ignore it and use the transcription.
        response_modalities=["TEXT"] if "transcribe" in model else ["AUDIO"],
        input_audio_transcription=transcription_cfg,
        system_instruction=SILENT_TRANSCRIBER,
    )

    segments: list[str] = []
    sent_bytes = 0
    current = ""            # fragments of the sentence being spoken
    last_text_at = 0.0
    audio_finished = asyncio.Event()
    settled = asyncio.Event()  # set once everything heard so far has been finalised

    async def finalise() -> None:
        nonlocal current
        text = current.strip()
        current = ""
        if text:
            segments.append(text)
            await on_event({"type": "final", "text": text})
        if audio_finished.is_set():
            settled.set()

    async with client.aio.live.connect(model=model, config=live_config) as session:

        async def sender() -> None:
            nonlocal sent_bytes
            while (chunk := await audio_q.get()) is not None:
                sent_bytes += len(chunk)
                await session.send_realtime_input(audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000"))
            await session.send_realtime_input(audio_stream_end=True)
            audio_finished.set()

        async def receiver() -> None:
            nonlocal current, last_text_at
            # receive() can end after a turn finishes, so keep re-entering until cancelled.
            while True:
                async for response in session.receive():
                    content = response.server_content
                    if not content:
                        continue
                    if content.interim_input_transcription and content.interim_input_transcription.text:
                        await on_event({"type": "interim", "text": content.interim_input_transcription.text})
                    if content.input_transcription and content.input_transcription.text:
                        current += content.input_transcription.text
                        last_text_at = time.monotonic()
                        await on_event({"type": "interim", "text": current.strip()})
                    if content.turn_complete or content.generation_complete:
                        await finalise()
                await asyncio.sleep(0.05)

        async def idle_flusher() -> None:
            while True:
                await asyncio.sleep(0.3)
                if current and time.monotonic() - last_text_at >= IDLE_FLUSH_S:
                    await finalise()

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver()), asyncio.create_task(idle_flusher())]
        try:
            await tasks[0]
            try:
                await asyncio.wait_for(settled.wait(), timeout=FINAL_GRACE_S)
            except asyncio.TimeoutError:
                pass
            await finalise()  # anything still pending when the grace period ends
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    return {"transcript": " ".join(segments), "segments": segments, "duration_s": round(sent_bytes / BYTES_PER_SECOND, 1)}


# ---------------------------------------------------------------- flash (chunked)

def _flash_transcribe(client, pcm: bytes, model: str | None = None) -> str:
    """Blocking call: audio in, text out. Returns '' when the model reports no speech."""
    from google.genai import types

    lang = " (the language is %s)" % config.TRANSCRIBE_LANGUAGE if config.TRANSCRIBE_LANGUAGE else ""
    response = client.models.generate_content(
        model=model or config.GEMINI_STT_MODEL,
        contents=[types.Part.from_bytes(data=wav_bytes(pcm), mime_type="audio/wav"), FLASH_PROMPT.format(lang=lang)],
    )
    text = (response.text or "").strip()
    return "" if NO_SPEECH in text.upper().replace(" ", "_") else text


async def _flash_session(audio_q, on_event: OnEvent, model: str) -> dict:
    client = make_client()
    segments: list[str] = []
    total_bytes = 0
    buf = bytearray()
    speaking = False
    quiet_s = 0.0
    previous: asyncio.Task | None = None

    def send_for_transcription(pcm: bytes) -> None:
        """Transcribe in the background, but report results in speaking order."""
        nonlocal previous
        earlier = previous

        async def run() -> None:
            text = await asyncio.to_thread(_flash_transcribe, client, pcm, model)
            if earlier:
                await asyncio.gather(earlier, return_exceptions=True)
            if text:
                segments.append(text)
                await on_event({"type": "final", "text": text})

        previous = asyncio.create_task(run())

    def flush() -> None:
        nonlocal buf, speaking, quiet_s
        pcm, buf, speaking, quiet_s = bytes(buf), bytearray(), False, 0.0
        if pcm:
            send_for_transcription(pcm)

    while (chunk := await audio_q.get()) is not None:
        total_bytes += len(chunk)
        seconds = len(chunk) / BYTES_PER_SECOND
        if _rms(chunk) > SPEECH_RMS:
            if not speaking:
                await on_event({"type": "interim", "text": "…"})
            speaking, quiet_s = True, 0.0
            buf += chunk
        elif speaking:
            buf += chunk
            quiet_s += seconds
            if quiet_s >= config.STT_FLASH_PAUSE_S:
                flush()
        if speaking and len(buf) / BYTES_PER_SECOND >= config.STT_FLASH_MAX_SEGMENT_S:
            flush()
    flush()
    if previous:
        await previous

    return {"transcript": " ".join(segments), "segments": segments, "duration_s": round(total_bytes / BYTES_PER_SECOND, 1)}


# ---------------------------------------------------------------- audio files

def file_model() -> str:
    """Model used for uploaded files: always a request/response model, never a streaming one."""
    main = config.GEMINI_STT_MODEL
    if "live" not in main.lower():
        return main
    backup = config.GEMINI_STT_FALLBACK_MODEL
    if not backup:
        raise config.ConfigError(
            f"GEMINI_STT_MODEL={main} streams live audio and cannot transcribe a file. "
            f"Set GEMINI_STT_FALLBACK_MODEL (for example a flash model) in {config.ENV_FILE}")
    return backup


def transcribe_pcm(pcm: bytes) -> dict:
    """Transcribe a whole recording (16 kHz mono PCM). Blocking. Long files are sent in pieces."""
    duration = round(len(pcm) / BYTES_PER_SECOND, 1)
    if not pcm:
        return {"mode": "gemini", "model": None, "transcript": "", "segments": [], "duration_s": 0.0}
    if not config.GEMINI_API_KEY:
        text = f"(mock transcript) received {duration}s of audio. Add GEMINI_API_KEY to inputs/.env for real text."
        return {"mode": "mock", "model": None, "transcript": text, "segments": [text], "duration_s": duration}

    model = file_model()
    client = make_client()
    step = FILE_PIECE_S * BYTES_PER_SECOND
    segments = [t for i in range(0, len(pcm), step) if (t := _flash_transcribe(client, pcm[i:i + step], model))]
    return {"mode": "gemini", "model": model, "transcript": " ".join(segments), "segments": segments,
            "duration_s": duration}
