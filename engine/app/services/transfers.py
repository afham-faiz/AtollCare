# Transfer lifecycle: vitals → NEWS2 → alerts → live briefing; crew notes; hospital questions and acceptance.
# Routers call this. Per-transfer locks serialise mutations (simulator loop vs. requests).
from __future__ import annotations

import asyncio
import logging
import random
import time as _time
import zlib
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.core import alerts as alerts_mod
from app.core import briefing as briefing_mod
from app.core import regions
from app.core.clock import fmt_local
from app.core.forecast import bucket_news2, forecast
from app.core.news2 import compute as compute_news2
from app.core.vitals import LOW_CONFIDENCE, simulated_values, update_latest
from app.models import (
    Acceptance,
    AcceptRequest,
    Author,
    Briefing,
    CreateTransferRequest,
    DemoCase,
    Extraction,
    Intervention,
    MessageRequest,
    Monitoring,
    MonitoringSource,
    Note,
    NoteKind,
    NoteRequest,
    Patient,
    PreArrival,
    Region,
    RemoveInterventionRequest,
    Scan,
    ScanStatus,
    SimProfile,
    Transfer,
    TransferListItem,
    TransferStatus,
    TrendResponse,
    VitalsAck,
    VitalsReading,
    VitalsRequest,
    VitalsSource,
)
from app.services.context import AppError, Services

log = logging.getLogger("atollcare.transfers")
ACTIVE = {TransferStatus.preparing, TransferStatus.pending, TransferStatus.accepted}
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
NEWS2_LOOKBACK_MIN = 60
GEMINI_MIN_INTERVAL_S = 20.0
PREPARE_OPTIONS = ["Cath lab", "Stroke team + CT", "Trauma team", "Theatre", "ICU bed", "Blood products", "Resus bay"]


def scan_summary(scan: Scan) -> str:
    """One line for the timeline: Presage numbers (weak ones marked unscored) and the signs Gemini saw on the video."""
    parts: list[str] = []
    v = scan.vitals
    if v is not None and v.source == "presage":
        for label, value, unit, quality in (("heart rate", v.heart_rate_bpm, " bpm", v.heart_rate_quality),
                                            ("breathing", v.respiration_rate_bpm, "/min", v.respiration_quality)):
            if value is not None:
                weak = (quality or 0.0) < LOW_CONFIDENCE
                parts.append(f"{label} {value}{unit}" + (" (weak signal, not scored)" if weak else ""))
    measured = "; ".join(parts) if parts else "heart and breathing rate not measured"
    if scan.signs is None or any(i.startswith("inspection_failed") for i in scan.signs.issues):
        return f"{measured}. Visible signs not checked."
    seen = [f.label for f in scan.signs.findings if f.finding == "present"]
    described = {c.cue_id for c in scan.signs.plan.cues if c.source == "transcript"}
    missing = [f.label for f in scan.signs.findings if f.finding == "absent" and f.cue_id in described]
    checked = any(f.finding == "absent" for f in scan.signs.findings)
    signs = (f"Seen on video: {', '.join(seen)}." if seen else "No checklist signs seen." if checked
             else "The video didn't show enough to check visible signs.")
    if missing:
        signs += f" Described but not seen: {', '.join(missing)}."
    return f"{measured}. {signs}"

# simulated contactless profile picked from the complaint (DEMO ASSUMPTION)
PROFILES = [
    (r"chest|crushing|stemi", SimProfile(heart_rate=100, heart_rate_per_hour=22, resp_rate=20, resp_rate_per_hour=6, hrv_rmssd=22)),
    (r"slurred|droop|weakness|stroke", SimProfile(heart_rate=86, heart_rate_per_hour=5, resp_rate=17, resp_rate_per_hour=2, hrv_rmssd=30)),
    (r"bleed|fracture|fell|fall|trauma|crash", SimProfile(heart_rate=116, heart_rate_per_hour=20, resp_rate=22, resp_rate_per_hour=6, hrv_rmssd=18)),
    (r"breath|wheez|asthma", SimProfile(heart_rate=108, heart_rate_per_hour=10, resp_rate=26, resp_rate_per_hour=4, hrv_rmssd=20)),
]


def describe(r: VitalsReading) -> str:
    """'SpO₂ 95%, on air, BP 104, T 36.8 °C, ACVPU A' — for the timeline."""
    parts: list[str] = []
    for field, fmt in [
        ("heart_rate", "HR {:g}"), ("resp_rate", "RR {:g}"), ("spo2", "SpO₂ {:g}%"), ("systolic_bp", "BP {:g}"),
        ("temperature_c", "T {:g} °C"),
    ]:
        v = getattr(r, field)
        if v is not None:
            parts.append(fmt.format(v))
    if r.on_oxygen is not None:
        parts.append("on oxygen" if r.on_oxygen else "on air")
    if r.consciousness is not None:
        parts.append(f"ACVPU {r.consciousness.value}")
    return ", ".join(parts)


def profile_for(complaint: str) -> SimProfile:
    import re

    text = complaint.lower()
    return next((p for pattern, p in PROFILES if re.search(pattern, text)), SimProfile())


class TransferService:
    def __init__(self, svc: Services, runner=None) -> None:
        self.svc = svc
        self.runner = runner  # ScanRunner (app.services.intakes), shared with pre-arrival packets
        self.repo = svc.repo
        self.locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._gemini_at: dict[UUID, float] = {}
        self._briefing_tasks: dict[UUID, asyncio.Task] = {}
        self._last_sim: dict[UUID, float] = {}

    # ---------------------------------------------------------------- helpers
    def now(self) -> datetime:
        return self.svc.clock.now()

    def region_of(self, t: Transfer) -> Region:
        r = regions.region(t.region_id)
        if r is None:
            raise AppError("unknown_region", f"Region {t.region_id} is not installed", 500)
        return r

    def label(self, t: Transfer, facility_id: str) -> str:
        f = regions.facility(t.region_id, facility_id)
        return f.short_name if f else facility_id

    async def _load(self, transfer_id: UUID) -> Transfer:
        t = await self.repo.get_transfer(transfer_id)
        if t is None:
            raise AppError("not_found", f"Transfer {transfer_id} not found", 404)
        return t

    async def get(self, transfer_id: UUID) -> Transfer:
        t = await self._load(transfer_id)
        t.notes = await self.repo.get_notes(transfer_id)
        t.vitals = await self.repo.get_vitals(transfer_id, 120)
        return t

    async def _save(self, t: Transfer) -> None:
        t.updated_at = self.now()
        await self.repo.update_transfer(t)

    async def _note(
        self, t: Transfer, author: Author, kind: NoteKind, text: str, *, at: datetime | None = None,
        reply_to: UUID | None = None, extraction: Extraction | None = None, extracted_by: str | None = None,
        audio_url: str | None = None,
    ) -> Note:
        note = Note(
            id=uuid4(), transfer_id=t.id, at=at or self.now(), author=author, kind=kind, text=text, reply_to=reply_to,
            extraction=extraction, extracted_by=extracted_by, audio_url=audio_url,  # type: ignore[arg-type]
        )
        await self.repo.add_note(note)
        t.notes.append(note)
        return note

    async def _code(self) -> str:
        existing = {t.code for t in await self.repo.list_transfers()}
        while True:
            code = "AC-" + "".join(random.choices(CODE_ALPHABET, k=4))
            if code not in existing:
                return code

    def _mode_label(self, t: Transfer) -> str:
        return regions.modes()[t.mode].label

    # ---------------------------------------------------------------- creation
    async def create(self, req: CreateTransferRequest, at: datetime | None = None) -> Transfer:
        region = regions.region(self.svc.clock.state.region_id)
        if region is None:
            raise AppError("unknown_region", "Selected region is not installed", 500)
        origin = regions.facility(region.id, req.origin_id)
        dest = regions.facility(region.id, req.destination_id)
        if origin is None or dest is None:
            raise AppError("unknown_facility", f"Pick a origin and destination in {region.name}", 422)
        if origin.id == dest.id:
            raise AppError("same_place", "Origin and destination must differ", 422)
        if req.mode not in region.modes:
            raise AppError("mode_unavailable", f"{req.mode.value} is not available in {region.name}", 422)
        now = at or self.now()
        km, eta = regions.journey(origin, dest, req.mode, now)
        t = Transfer(
            id=uuid4(), code=await self._code(), region_id=region.id, created_at=now, updated_at=now,
            status=TransferStatus.preparing, patient=req.patient, complaint=req.complaint.strip(),
            origin_id=origin.id, destination_id=dest.id, mode=req.mode, departed_at=now, eta=eta, distance_km=km,
            position=regions.point(origin), origin_point=regions.point(origin), destination_point=regions.point(dest),
            monitoring=Monitoring(source=MonitoringSource.simulated), sim_profile=profile_for(req.complaint),
        )
        await self.repo.insert_transfer(t)
        await self._note(
            t, Author.system, NoteKind.event,
            f"Transfer started · {origin.short_name} → {dest.short_name} by {self._mode_label(t).lower()} · "
            f"ETA {fmt_local(eta, region.timezone)}",
            at=now,
        )
        await self._template_briefing(t)
        await self._save(t)
        self._schedule_briefing(t.id)
        return await self.get(t.id)

    # ---------------------------------------------------------------- vitals
    async def add_vitals(self, transfer_id: UUID, req: VitalsRequest) -> VitalsAck:
        async with self.locks[transfer_id]:
            t = await self._load(transfer_id)
            if t.status == TransferStatus.closed:
                raise AppError("closed", "Transfer is closed", 409)
            await self._ingest(t, req)
            await self._save(t)
            return VitalsAck(news2=t.news2, alerts=t.alerts, monitoring=t.monitoring)

    async def _ingest(self, t: Transfer, req: VitalsRequest, *, live: bool = True) -> VitalsReading:
        now = self.now()
        data = req.model_dump(exclude={"recorded_at", "hint"})
        reading = VitalsReading(
            id=uuid4(), transfer_id=t.id, recorded_at=req.recorded_at or now,
            low_quality=req.confidence is not None and req.confidence < LOW_CONFIDENCE, **data,
        )
        if all(getattr(reading, f) is None for f in ("heart_rate", "resp_rate", "hrv_rmssd", "spo2", "on_oxygen",
                                                       "systolic_bp", "temperature_c", "consciousness")):
            raise AppError("empty_reading", "No vitals in the reading", 422)
        await self.repo.add_vitals(reading)
        t.latest = update_latest(t.latest, reading)
        if reading.source == VitalsSource.presage and live:  # a scan's reading says nothing about the live camera
            t.monitoring.source = MonitoringSource.presage
            t.monitoring.hint = req.hint
        if reading.source in (VitalsSource.presage, VitalsSource.simulated) and live:
            t.monitoring.last_reading_at = reading.recorded_at
        if reading.source == VitalsSource.manual:
            await self._note(t, Author.crew, NoteKind.event, "Vitals entered: " + describe(reading), at=reading.recorded_at)
        await self._reassess(t)
        return reading

    async def _reassess(self, t: Transfer) -> None:
        now = self.now()
        # Clinical scoring sees only what was measured (Presage, crew). Simulated readings keep the demo moving on
        # screen, labelled, but never raise an alert, move NEWS2 or feed the forecast.
        readings = [r for r in await self.repo.get_vitals(t.id, 240) if r.source != VitalsSource.simulated]
        measured_latest = {k: v for k, v in t.latest.items() if v.source != VitalsSource.simulated}
        before_total = t.news2.total if t.news2 else None
        t.news2 = compute_news2(readings, now, NEWS2_LOOKBACK_MIN)
        trend = await self._trend_buckets(t, 60, readings)
        fc = forecast(trend, now, t.eta)
        before = t.alerts
        t.alerts = alerts_mod.evaluate(t.news2, measured_latest, fc, before, now)
        announce = alerts_mod.new_alerts(before, t.alerts, t.alerts_announced, now)
        for a in announce:
            t.alerts_announced[a.code] = now
            await self._note(t, Author.system, NoteKind.alert, a.text)
        changed = (t.news2.total if t.news2 else None) != before_total or bool(announce)
        if changed:
            await self._template_briefing(t, keep_gemini=True)
            self._schedule_briefing(t.id)

    async def _trend_buckets(self, t: Transfer, window_min: int, readings: list[VitalsReading] | None = None):
        buckets, _ = await self.repo.vitals_trend(t.id, self.now() - timedelta(minutes=window_min))
        extra: dict[str, Any] = {}
        for r in reversed(readings or await self.repo.get_vitals(t.id, 120)):
            if r.consciousness is not None and "consciousness" not in extra:
                extra["consciousness"] = r.consciousness.value
            if r.on_oxygen is not None and "on_oxygen" not in extra:
                extra["on_oxygen"] = r.on_oxygen
        return bucket_news2(buckets, extra)

    async def trend(self, transfer_id: UUID, window_min: int) -> TrendResponse:
        t = await self._load(transfer_id)
        started = _time.perf_counter()
        _, source = await self.repo.vitals_trend(t.id, self.now() - timedelta(minutes=window_min))
        query_ms = round((_time.perf_counter() - started) * 1000, 1)
        filled = await self._trend_buckets(t, window_min)
        return TrendResponse(buckets=filled, source=source, query_ms=query_ms,  # type: ignore[arg-type]
                             forecast=forecast(filled, self.now(), t.eta))

    async def set_monitoring(self, transfer_id: UUID, source: MonitoringSource) -> Transfer:
        async with self.locks[transfer_id]:
            t = await self._load(transfer_id)
            if t.monitoring.source != source:
                t.monitoring.source = source
                t.monitoring.hint = None
                text = {
                    MonitoringSource.presage: "Contactless monitoring: Presage camera connected",
                    MonitoringSource.simulated: "Contactless monitoring: simulated (Presage bridge not connected)",
                    MonitoringSource.scan: "Contactless monitoring: 60-second Presage scans",
                    MonitoringSource.off: "Contactless monitoring paused",
                }[source]
                await self._note(t, Author.system, NoteKind.event, text)
            await self._save(t)
        return await self.get(transfer_id)

    # ---------------------------------------------------------------- briefing
    async def _template_briefing(self, t: Transfer, keep_gemini: bool = False) -> None:
        if keep_gemini and t.briefing and t.briefing.generated_by == "gemini":
            return  # the Gemini refresh replaces it shortly; never downgrade a fresher AI briefing to template
        r = self.region_of(t)
        full = t.model_copy(update={"notes": await self.repo.get_notes(t.id)})
        data = briefing_mod.inputs(full, self.label(t, t.origin_id), self.label(t, t.destination_id), self._mode_label(t),
                                   r.timezone)
        b = briefing_mod.template(full, data, self.now())
        b.input_hash = briefing_mod.inputs_hash(data)
        t.briefing = b

    def _schedule_briefing(self, transfer_id: UUID, force: bool = False) -> None:
        if self.svc.gemini.status != "real":
            return
        task = self._briefing_tasks.get(transfer_id)
        if task and not task.done():
            return
        self._briefing_tasks[transfer_id] = asyncio.create_task(self._gemini_briefing(transfer_id, force))

    async def _gemini_briefing(self, transfer_id: UUID, force: bool) -> None:
        try:
            wait = GEMINI_MIN_INTERVAL_S - (_time.monotonic() - self._gemini_at.get(transfer_id, 0))
            if wait > 0 and not force:
                await asyncio.sleep(wait)
            async with self.locks[transfer_id]:
                t = await self.get(transfer_id)
                r = self.region_of(t)
                data = briefing_mod.inputs(t, self.label(t, t.origin_id), self.label(t, t.destination_id),
                                           self._mode_label(t), r.timezone)
                h = briefing_mod.inputs_hash(data)
                if t.briefing and t.briefing.generated_by == "gemini" and t.briefing.input_hash == h:
                    return
            self._gemini_at[transfer_id] = _time.monotonic()
            gb, err = await self.svc.gemini.briefing(data)
            async with self.locks[transfer_id]:
                t = await self._load(transfer_id)
                if gb is not None:
                    t.briefing = Briefing(**gb.model_dump(), generated_by="gemini", generated_at=self.now(), input_hash=h)
                elif err and not self.svc.caches.get(f"briefing_err:{transfer_id}"):
                    self.svc.caches[f"briefing_err:{transfer_id}"] = True
                    await self._note(t, Author.system, NoteKind.event, f"{err} — showing template briefing")
                await self._save(t)
        except Exception:
            log.exception("briefing refresh failed")

    # ---------------------------------------------------------------- notes & messages
    async def _extract(self, text: str) -> tuple[Extraction, str]:
        if self.svc.gemini.status == "real":
            ge, _err = await self.svc.gemini.extract(text)
            if ge is not None:
                def cap(items: list[str], n: int) -> list[str]:  # same casing as the rule-based chips
                    return [i.strip()[:1].upper() + i.strip()[1:] for i in items if i.strip()][:n]

                return Extraction(observations=cap(ge.observations, 6), interventions=cap(ge.interventions, 4)), "gemini"
        return briefing_mod.extract(text), "rules"

    async def add_note(self, transfer_id: UUID, req: NoteRequest, at: datetime | None = None) -> Transfer:
        extraction, by = await self._extract(req.text)
        async with self.locks[transfer_id]:
            t = await self.get(transfer_id)
            if req.reply_to and not any(n.id == req.reply_to for n in t.notes):
                raise AppError("unknown_question", "That question no longer exists", 422)
            kind = NoteKind.answer if req.reply_to else NoteKind(req.kind)
            note = await self._note(t, Author.crew, kind, req.text.strip(), at=at, reply_to=req.reply_to,
                                    extraction=extraction, extracted_by=by)
            for item in extraction.interventions:
                t.interventions.append(Intervention(at=note.at, text=item, note_id=note.id))
            await self._template_briefing(t, keep_gemini=True)
            await self._save(t)
        self._schedule_briefing(transfer_id, force=True)
        return await self.get(transfer_id)

    # ---------------------------------------------------------------- pre-arrival packet and scans
    async def _record_scan_vitals(self, t: Transfer, scan: Scan) -> None:
        """A finished scan's heart and breathing rate become two Presage readings (each carries its own quality),
        timed when the clip was recorded. Mock or unavailable results never become readings."""
        v = scan.vitals
        if scan.recorded or v is None:
            return
        if v.source == "presage":
            for field, value, quality in (("heart_rate", v.heart_rate_bpm, v.heart_rate_quality),
                                          ("resp_rate", v.respiration_rate_bpm, v.respiration_quality)):
                if value is not None:
                    await self._ingest(t, VitalsRequest(source=VitalsSource.presage, recorded_at=scan.at,
                                                        confidence=round(quality or 0.0, 3), **{field: value}),
                                       live=False)
        scan.recorded = True

    async def _note_scan(self, t: Transfer, scan: Scan, what: str) -> None:
        """Once a scan is finished, one line on the timeline: what was measured and what was seen. The briefing reads
        the timeline, so this is also how a scan reaches it."""
        if scan.noted or scan.status != ScanStatus.done:
            return
        scan.noted = True
        await self._note(t, Author.system, NoteKind.event, f"{what}: {scan_summary(scan)}", at=scan.at)

    async def attach_pre_arrival(self, transfer_id: UUID, packet: PreArrival) -> None:
        async with self.locks[transfer_id]:
            t = await self._load(transfer_id)
            t.pre_arrival = packet
            if packet.account:
                await self._note(t, Author.companion, NoteKind.text, packet.account, at=packet.sent_at or self.now())
            for s in packet.scans:
                await self._record_scan_vitals(t, s)
                await self._note_scan(t, s, "Pre-arrival video")
            await self._template_briefing(t, keep_gemini=True)
            await self._save(t)
        self._schedule_briefing(transfer_id, force=True)

    async def sync_pre_arrival_scan(self, transfer_id: UUID, scan: Scan) -> None:
        """A pre-arrival scan finished after the transfer started: update the transfer's copy and record its vitals."""
        async with self.locks[transfer_id]:
            t = await self._load(transfer_id)
            if t.pre_arrival is None:
                return
            mine = next((s for s in t.pre_arrival.scans if s.id == scan.id), None)
            copy = scan.model_copy(deep=True, update={"recorded": mine.recorded if mine else False,
                                                      "noted": mine.noted if mine else False})
            t.pre_arrival.scans = [copy if s.id == scan.id else s for s in t.pre_arrival.scans]
            await self._record_scan_vitals(t, copy)
            await self._note_scan(t, copy, "Pre-arrival video")
            await self._save(t)

    async def add_scan(self, transfer_id: UUID, video: bytes) -> Transfer:
        if not video:
            raise AppError("empty_upload", "No video was received", 400)
        if self.runner is None:
            raise AppError("scans_unavailable", "Scanning is not set up on this engine", 501)
        async with self.locks[transfer_id]:
            t = await self._load(transfer_id)
            if t.status in (TransferStatus.arrived, TransferStatus.closed):
                raise AppError("finished", "This transfer has finished", 409)
            scan = Scan(id=uuid4(), at=self.now(), stage="Uploading")
            t.scans.append(scan)
            await self._save(t)
        self.runner.start(scan, video, t.complaint, t.patient.age, self._mutate_scan(transfer_id))
        return await self.get(transfer_id)

    def _mutate_scan(self, transfer_id: UUID):
        async def mutate(scan_id: UUID, fn) -> None:
            async with self.locks[transfer_id]:
                t = await self._load(transfer_id)
                scan = next((s for s in t.scans if s.id == scan_id), None)
                if scan is None:
                    return
                fn(scan)
                await self._record_scan_vitals(t, scan)
                await self._note_scan(t, scan, "Crew scan")
                await self._save(t)

        return mutate

    async def remove_intervention(self, transfer_id: UUID, req: RemoveInterventionRequest) -> Transfer:
        async with self.locks[transfer_id]:
            t = await self._load(transfer_id)
            keep = [i for i in t.interventions if not (i.note_id == req.note_id and i.text == req.text)]
            if len(keep) == len(t.interventions):
                raise AppError("unknown_intervention", "That item is no longer in the handoff", 404)
            t.interventions = keep
            await self._note(t, Author.crew, NoteKind.event, f"Removed from handoff: {req.text}")
            await self._template_briefing(t)
            await self._save(t)
        self._schedule_briefing(transfer_id, force=True)
        return await self.get(transfer_id)

    async def voice_note(self, transfer_id: UUID, audio: bytes, filename: str, content_type: str,
                         reply_to: UUID | None) -> Transfer:
        try:
            result = await self.svc.elevenlabs.transcribe(audio, filename, content_type, None)
        except Exception as exc:
            raise AppError("stt_failed", f"Transcription failed ({type(exc).__name__}) — try again or type", 502) from exc
        if result is None:
            raise AppError("stt_unavailable", "Server speech-to-text is not configured — use browser dictation", 501)
        text, _lang = result
        if not text:
            raise AppError("empty_transcript", "Didn't catch that — please try again", 422)
        return await self.add_note(transfer_id, NoteRequest(text=text, kind="voice", reply_to=reply_to))

    async def message(self, transfer_id: UUID, req: MessageRequest) -> Transfer:
        async with self.locks[transfer_id]:
            t = await self.get(transfer_id)
            dest = self.label(t, t.destination_id)
            prefix = f"{req.sender} ({dest})" if req.sender else dest
            await self._note(t, Author.hospital, NoteKind(req.kind), f"{prefix}: {req.text.strip()}")
            await self._save(t)
        self._schedule_briefing(transfer_id)
        return await self.get(transfer_id)

    async def handoff(self, transfer_id: UUID) -> Transfer:
        """Crew sends the handoff: the transfer appears at the receiving hospital. Idempotent."""
        async with self.locks[transfer_id]:
            t = await self.get(transfer_id)
            if t.status != TransferStatus.preparing:
                return t
            now = self.now()
            t.status = TransferStatus.pending
            t.handoff_at = now
            await self._note(t, Author.crew, NoteKind.event, f"Handoff sent to {self.label(t, t.destination_id)}", at=now)
            await self._save(t)
        self._schedule_briefing(transfer_id, force=True)
        return await self.get(transfer_id)

    async def accept(self, transfer_id: UUID, req: AcceptRequest) -> Transfer:
        async with self.locks[transfer_id]:
            t = await self.get(transfer_id)
            if t.status != TransferStatus.pending:
                raise AppError("invalid_state", f"Transfer is {t.status.value}", 409)
            now = self.now()
            t.status = TransferStatus.accepted
            t.acceptance = Acceptance(by=req.by.strip(), at=now, prepare=req.prepare, message=req.message)
            dest = self.label(t, t.destination_id)
            text = f"{dest} accepted — {req.by.strip()}."
            if req.prepare:
                text += f" Preparing: {', '.join(p.lower() for p in req.prepare)}."
            if req.message:
                text += f" {req.message.strip()}"
            await self._note(t, Author.hospital, NoteKind.message, text, at=now)
            await self._save(t)
        return await self.get(transfer_id)

    async def arrive(self, transfer_id: UUID, at: datetime | None = None, auto: bool = False) -> Transfer:
        async with self.locks[transfer_id]:
            t = await self.get(transfer_id)
            if t.status not in ACTIVE:
                return t
            await self._arrive(t, at or self.now(), auto)
            await self._save(t)
        return await self.get(transfer_id)

    async def _arrive(self, t: Transfer, at: datetime, auto: bool) -> None:
        t.status = TransferStatus.arrived
        t.arrived_at = at
        t.progress = 1
        t.position = t.destination_point
        t.monitoring.source = MonitoringSource.off
        await self._note(t, Author.system, NoteKind.event,
                         f"Arrived at {self.label(t, t.destination_id)}{' (ETA reached)' if auto else ''} — handover", at=at)

    async def close(self, transfer_id: UUID) -> Transfer:
        async with self.locks[transfer_id]:
            t = await self.get(transfer_id)
            if t.status == TransferStatus.closed:
                return t
            if t.status in ACTIVE:
                await self._arrive(t, self.now(), auto=False)
            t.status = TransferStatus.closed
            await self._note(t, Author.system, NoteKind.event, "Transfer closed")
            await self._save(t)
        return await self.get(transfer_id)

    # ---------------------------------------------------------------- listing
    async def list(self, status: str | None) -> list[TransferListItem]:
        wanted = {s.strip() for s in status.split(",")} if status else None
        items: list[TransferListItem] = []
        for t in await self.repo.list_transfers():
            if wanted and t.status.value not in wanted:
                continue
            notes = await self.repo.get_notes(t.id)
            answered = {n.reply_to for n in notes if n.reply_to}
            level = None
            if t.alerts:
                level = "critical" if any(a.level.value == "critical" for a in t.alerts) else "warning"

            def num(field: str, latest=t.latest) -> float | None:
                lv = latest.get(field)
                return float(lv.value) if lv is not None and isinstance(lv.value, (int, float)) and not isinstance(lv.value, bool) else None

            items.append(TransferListItem(
                id=t.id, code=t.code, region_id=t.region_id, status=t.status, patient=t.patient, complaint=t.complaint,
                suspected_condition=t.briefing.suspected_condition if t.briefing else None,
                origin_id=t.origin_id, destination_id=t.destination_id, mode=t.mode, eta=t.eta, progress=t.progress,
                news2_total=t.news2.total if t.news2 else None, news2_band=t.news2.band if t.news2 else None,
                alert_level=level, heart_rate=num("heart_rate"), resp_rate=num("resp_rate"),  # type: ignore[arg-type]
                monitoring=t.monitoring.source,
                unanswered_questions=sum(1 for n in notes if n.kind == NoteKind.question and n.id not in answered),
                updated_at=t.updated_at,
            ))
        order = {"pending": 0, "accepted": 1, "preparing": 2, "arrived": 3, "closed": 4}
        return sorted(items, key=lambda i: (order[i.status.value], i.eta))

    # ---------------------------------------------------------------- simulator tick
    async def tick(self) -> None:
        """Advance position / ETA progress, emit simulated contactless vitals, auto-arrive at ETA."""
        now = self.now()
        interval = self.svc.settings.simulated_vitals_interval_s
        for t in await self.repo.list_transfers():
            if t.status not in ACTIVE:
                continue
            async with self.locks[t.id]:
                cur = await self._load(t.id)
                if cur.status not in ACTIVE:
                    continue
                total = (cur.eta - cur.departed_at).total_seconds() or 1
                cur.progress = round(max(0.0, min(1.0, (now - cur.departed_at).total_seconds() / total)), 4)
                cur.position = regions.interpolate(cur.origin_point, cur.destination_point, cur.progress)
                if now >= cur.eta:
                    await self._arrive(cur, cur.eta, auto=True)
                    await self._save(cur)
                    continue
                due = _time.monotonic() - self._last_sim.get(cur.id, 0) >= interval
                if cur.monitoring.source == MonitoringSource.simulated and due:
                    self._last_sim[cur.id] = _time.monotonic()
                    values = simulated_values(cur.sim_profile, cur.departed_at, now, zlib.crc32(cur.code.encode()))
                    await self._ingest(cur, VitalsRequest(source=VitalsSource.simulated, confidence=0.9, **values))
                await self._save(cur)

    # ---------------------------------------------------------------- prepared demo cases
    def demo_cases(self) -> list[DemoCase]:
        out = []
        for c in regions.cases():
            base = c.get("baseline_vitals")
            suggested = describe(VitalsReading(id=uuid4(), transfer_id=uuid4(), recorded_at=self.now(), source=VitalsSource.manual,
                                               **base)) if base else None
            out.append(DemoCase(**{k: v for k, v in c.items() if k in DemoCase.model_fields}, suggested_vitals=suggested))
        return out

    async def start_case(self, case_id: str | None = None) -> Transfer:
        """Start a prepared case in its region with patient, complaint and route filled in — and nothing else. Vitals
        come from the camera or from the presenter typing the case's suggested values; nothing is pre-entered as if
        the crew had measured it."""
        if case_id is None:
            region_id = self.svc.clock.state.region_id
            c = next((x for x in regions.cases() if x["region_id"] == region_id), None)
        else:
            c = regions.case(case_id)
        if c is None:
            raise AppError("no_case", "No prepared case found", 404)
        self.svc.clock.state.region_id = c["region_id"]
        await self.repo.set_demo_state(self.svc.clock.state)
        t = await self.create(
            CreateTransferRequest(patient=Patient(**c["patient"]), complaint=c["complaint"], origin_id=c["origin_id"],
                                  destination_id=c["destination_id"], mode=c["mode"]),
        )
        async with self.locks[t.id]:
            cur = await self._load(t.id)
            cur.sim_profile = SimProfile(**c.get("profile", {}))
            await self._save(cur)
        return await self.get(t.id)
