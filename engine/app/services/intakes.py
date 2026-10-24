# Pre-arrival packets (Part 1, from Percy's services) and recorded scans. The companion's phone captures once — who the
# patient is, what happened in their words, one ~60 s clip — and the transfer started from it carries all of it.
#
# A scan is one recorded clip, analysed twice in parallel from the same video:
#   Gemini checks it for visible signs (grounded: every "seen" cites frames)   — usually done in 10–30 s
#   Presage measures heart and breathing rate from it (real-time playback)      — about as long as the clip
# Each part is saved the moment it finishes, so the screen fills in as results land. The video is never stored;
# a shrunken copy stays in memory briefly so the sign check can re-run when the companion's account arrives.
from __future__ import annotations

import asyncio
import logging
import random
import re
from collections import OrderedDict, defaultdict
from collections.abc import Awaitable, Callable
from datetime import datetime
from uuid import UUID, uuid4

from app.core import regions
from app.intake.ocr_service import parse_identity_doc
from app.intake.rppg_extractor import bridge_ready, extract_vitals_from_video
from app.intake.transcription import transcribe_pcm
from app.intake.video_prep import Frame, audio_to_pcm, downsample_video
from app.intake.vqa_evaluator import run_visual_cue_session
from app.models import (
    CreateIntakeRequest,
    CreateTransferRequest,
    Intake,
    IntakeStatus,
    PreArrival,
    Scan,
    ScanStatus,
    StartTransferRequest,
    Transfer,
    UpdateIntakeRequest,
)
from app.services.context import AppError, Services

log = logging.getLogger("atollcare.intake")
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CLIP_CACHE = 12  # shrunken clips kept in memory for re-checking signs; never written to disk
MAX_CLIP_BYTES = 150 * 1024 * 1024

MutateScan = Callable[[UUID, Callable[[Scan], None]], Awaitable[None]]


def first_sentence(text: str, limit: int = 120) -> str:
    """Fallback one-line complaint when Gemini is off: the first sentence, trimmed."""
    s = re.split(r"(?<=[.!?])\s", text.strip(), maxsplit=1)[0]
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


class ScanRunner:
    """Runs a scan's two analyses and saves each result through `mutate` as it finishes."""

    def __init__(self, svc: Services) -> None:
        self.svc = svc
        self.clips: OrderedDict[UUID, bytes] = OrderedDict()
        self.tasks: set[asyncio.Task] = set()

    def start(self, scan: Scan, raw: bytes, account: str, age: int | None, mutate: MutateScan,
              on_vitals: Callable[[Scan], Awaitable[None]] | None = None) -> None:
        task = asyncio.create_task(self._run(scan.id, raw, account, age, mutate, on_vitals))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    def recheck_signs(self, scan_id: UUID, account: str, age: int | None, mutate: MutateScan) -> bool:
        """Run the sign check again with a new account (the account changes which signs count as 'reported')."""
        small = self.clips.get(scan_id)
        if small is None:
            return False
        task = asyncio.create_task(self._signs(scan_id, small, account, age, mutate))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return True

    def _remember(self, scan_id: UUID, small: bytes) -> None:
        self.clips[scan_id] = small
        while len(self.clips) > CLIP_CACHE:
            self.clips.popitem(last=False)

    async def _run(self, scan_id: UUID, raw: bytes, account: str, age: int | None, mutate: MutateScan,
                   on_vitals: Callable[[Scan], Awaitable[None]] | None) -> None:
        try:
            await mutate(scan_id, lambda s: setattr(s, "stage", "Preparing the video"))
            small = await asyncio.to_thread(downsample_video, raw)
            self._remember(scan_id, small)
            await mutate(scan_id, lambda s: setattr(s, "stage", "Checking visible signs and measuring vitals"))
            await asyncio.gather(self._signs(scan_id, small, account, age, mutate),
                                 self._vitals(scan_id, small, mutate, on_vitals))
            await mutate(scan_id, lambda s: (setattr(s, "status", ScanStatus.done), setattr(s, "stage", None)))
        except Exception as exc:
            log.exception("scan %s failed", scan_id)
            message = f"{type(exc).__name__}: {str(exc)[:200]}"
            await mutate(scan_id, lambda s: (setattr(s, "status", ScanStatus.failed), setattr(s, "stage", None),
                                             setattr(s, "error", message)))

    async def _signs(self, scan_id: UUID, small: bytes, account: str, age: int | None, mutate: MutateScan) -> None:
        started = asyncio.get_running_loop().time()
        report, frames = await asyncio.to_thread(run_visual_cue_session, small, account, age)
        evidence = await self._save_evidence(scan_id, report, frames)
        seconds = round(asyncio.get_running_loop().time() - started, 1)

        def apply(s: Scan) -> None:
            s.signs, s.evidence = report, evidence
            s.seconds = {**s.seconds, "signs": seconds}

        await mutate(scan_id, apply)

    async def _save_evidence(self, scan_id: UUID, report, frames: list[Frame]) -> dict[str, str]:
        cited = {i for f in report.findings for i in f.evidence_frames}
        out: dict[str, str] = {}
        for fr in frames:
            if fr.index in cited:  # keep only the frames a conclusion depends on
                out[str(fr.index)] = await self.svc.storage.put(f"scans/{scan_id}/frame-{fr.index}.jpg", fr.jpeg,
                                                                 "image/jpeg")
        return out

    async def _vitals(self, scan_id: UUID, small: bytes, mutate: MutateScan,
                      on_vitals: Callable[[Scan], Awaitable[None]] | None) -> None:
        if not await asyncio.to_thread(bridge_ready):
            note = "The Presage bridge isn't running with an API key, so heart and breathing rate were not measured."
            await mutate(scan_id, lambda s: setattr(s, "vitals_note", note))
            return
        started = asyncio.get_running_loop().time()
        estimates = await asyncio.to_thread(extract_vitals_from_video, small)
        seconds = round(asyncio.get_running_loop().time() - started, 1)
        holder: dict[str, Scan] = {}

        def apply(s: Scan) -> None:
            s.vitals = estimates
            s.seconds = {**s.seconds, "presage": seconds}
            if estimates.heart_rate_bpm is None and estimates.respiration_rate_bpm is None:
                hints = [h.rstrip(".") + "." for h in estimates.diagnostics.get("hints") or []]
                s.vitals_note = " ".join(["Presage couldn't measure this clip.", *hints])
            holder["scan"] = s

        await mutate(scan_id, apply)
        if on_vitals and "scan" in holder:
            await on_vitals(holder["scan"])


class IntakeService:
    def __init__(self, svc: Services, transfers, runner: ScanRunner) -> None:
        self.svc = svc
        self.transfers = transfers  # TransferService
        self.runner = runner
        self.locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)

    def now(self) -> datetime:
        return self.svc.clock.now()

    async def _load(self, intake_id: UUID) -> Intake:
        i = await self.svc.repo.get_intake(intake_id)
        if i is None:
            raise AppError("not_found", f"Pre-arrival packet {intake_id} not found", 404)
        return i

    async def _save(self, i: Intake) -> Intake:
        i.updated_at = self.now()
        await self.svc.repo.save_intake(i)
        return i

    async def _code(self) -> str:
        taken = {i.code for i in await self.svc.repo.list_intakes()}
        while True:
            code = "PA-" + "".join(random.choices(CODE_ALPHABET, k=4))
            if code not in taken:
                return code

    def _editable(self, i: Intake) -> None:
        if i.status == IntakeStatus.started:
            raise AppError("already_started", "A transfer has already started from this packet", 409)

    # ---------------------------------------------------------------- the packet
    async def create(self, req: CreateIntakeRequest) -> Intake:
        region_id = req.region_id or self.svc.clock.state.region_id
        if regions.region(region_id) is None:
            raise AppError("unknown_region", f"Unknown region {region_id}", 422)
        if req.health_centre_id and regions.facility(region_id, req.health_centre_id) is None:
            raise AppError("unknown_facility", f"Unknown health centre {req.health_centre_id}", 422)
        now = self.now()
        i = Intake(id=uuid4(), code=await self._code(), region_id=region_id, created_at=now, updated_at=now,
                   health_centre_id=req.health_centre_id)
        await self.svc.repo.save_intake(i)
        return i

    async def get(self, intake_id: UUID) -> Intake:
        return await self._load(intake_id)

    async def list(self, status: str | None) -> list[Intake]:
        wanted = {s.strip() for s in status.split(",")} if status else None
        return [i for i in await self.svc.repo.list_intakes() if not wanted or i.status.value in wanted]

    async def update(self, intake_id: UUID, req: UpdateIntakeRequest) -> Intake:
        async with self.locks[intake_id]:
            i = await self._load(intake_id)
            self._editable(i)
            if req.patient is not None:
                i.patient = req.patient
            if req.health_centre_id is not None:
                if regions.facility(i.region_id, req.health_centre_id) is None:
                    raise AppError("unknown_facility", f"Unknown health centre {req.health_centre_id}", 422)
                i.health_centre_id = req.health_centre_id
            account_changed = req.account is not None and req.account.strip() != (i.account or "")
            if account_changed:
                await self._set_account(i, req.account.strip(), "text")
            await self._save(i)
        if account_changed:
            self._recheck(i)
        return i

    async def _set_account(self, i: Intake, text: str, source: str) -> None:
        i.account = text or None
        i.account_source = source if text else None  # type: ignore[assignment]
        i.complaint = (await self.svc.gemini.condense_account(text) or first_sentence(text)) if text else None

    def _recheck(self, i: Intake) -> None:
        for s in i.scans:
            self.runner.recheck_signs(s.id, i.account or "", i.patient.age, self._mutate_scan(i.id))

    async def account_voice(self, intake_id: UUID, audio: bytes, filename: str, content_type: str) -> Intake:
        if not audio:
            raise AppError("empty_upload", "No audio was received", 400)
        text = await self._transcribe(audio, filename, content_type)
        if not text:
            raise AppError("empty_transcript", "Didn't catch that — please try again, or type it", 422)
        async with self.locks[intake_id]:
            i = await self._load(intake_id)
            self._editable(i)
            await self._set_account(i, text, "voice")
            await self._save(i)
        self._recheck(i)
        return i

    async def _transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        """ElevenLabs Scribe (a dedicated speech model: verbatim, no paraphrase) when configured; Gemini otherwise."""
        if self.svc.elevenlabs.status == "real":
            try:
                result = await self.svc.elevenlabs.transcribe(audio, filename, content_type, None)
                if result and result[0].strip():
                    return result[0].strip()
            except Exception:  # noqa: BLE001 — fall through to Gemini
                log.warning("Scribe failed for an intake account; trying Gemini")
        from app.intake import config

        if not config.GEMINI_API_KEY:
            raise AppError("stt_unavailable", "No speech-to-text is configured — type the account instead", 501)
        pcm = await asyncio.to_thread(audio_to_pcm, audio)
        out = await asyncio.to_thread(transcribe_pcm, pcm)
        return (out.get("transcript") or "").replace("NO_SPEECH", "").strip()

    async def id_photo(self, intake_id: UUID, image: bytes) -> Intake:
        if not image:
            raise AppError("empty_upload", "No photo was received", 400)
        identity = await asyncio.to_thread(parse_identity_doc, image)
        async with self.locks[intake_id]:
            i = await self._load(intake_id)
            self._editable(i)
            i.identity = identity
            if identity.age is not None and i.patient.age is None:
                i.patient = i.patient.model_copy(update={"age": identity.age})
            await self._save(i)
        return i

    async def add_scan(self, intake_id: UUID, video: bytes) -> Intake:
        if not video:
            raise AppError("empty_upload", "No video was received", 400)
        if len(video) > MAX_CLIP_BYTES:
            raise AppError("too_large", "That video is too large — record about 60 seconds", 413)
        async with self.locks[intake_id]:
            i = await self._load(intake_id)
            self._editable(i)
            scan = Scan(id=uuid4(), at=self.now(), stage="Uploading")
            i.scans.append(scan)
            await self._save(i)
        self.runner.start(scan, video, i.account or "", i.patient.age, self._mutate_scan(intake_id))
        return i

    def _mutate_scan(self, intake_id: UUID):
        async def mutate(scan_id: UUID, fn: Callable[[Scan], None]) -> None:
            async with self.locks[intake_id]:
                i = await self.svc.repo.get_intake(intake_id)
                if i is None:
                    return
                for s in i.scans:
                    if s.id == scan_id:
                        fn(s)
                await self._save(i)
                # a packet already turned into a transfer keeps the transfer's copy in step
                if i.transfer_id:
                    await self.transfers.sync_pre_arrival_scan(i.transfer_id, next(s for s in i.scans if s.id == scan_id))

        return mutate

    async def send(self, intake_id: UUID) -> Intake:
        async with self.locks[intake_id]:
            i = await self._load(intake_id)
            self._editable(i)
            if not (i.account or i.scans or i.identity):
                raise AppError("empty_packet", "Add at least a video, an account or an ID before sending", 422)
            if i.status == IntakeStatus.draft:
                i.status, i.sent_at = IntakeStatus.sent, self.now()
            return await self._save(i)

    async def start_transfer(self, intake_id: UUID, req: StartTransferRequest) -> Transfer:
        async with self.locks[intake_id]:
            i = await self._load(intake_id)
            self._editable(i)
            origin = req.origin_id or i.health_centre_id
            if not origin:
                raise AppError("origin_required", "Choose where the transfer starts", 422)
            t = await self.transfers.create(CreateTransferRequest(
                patient=i.patient, complaint=i.complaint or first_sentence(i.account or "") or "Pre-arrival packet",
                origin_id=origin, destination_id=req.destination_id, mode=req.mode,
            ))
            packet = PreArrival(intake_id=i.id, code=i.code, sent_at=i.sent_at, account=i.account, identity=i.identity,
                                scans=i.scans)
            await self.transfers.attach_pre_arrival(t.id, packet)
            i.status, i.transfer_id = IntakeStatus.started, t.id
            await self._save(i)
        return await self.transfers.get(t.id)
