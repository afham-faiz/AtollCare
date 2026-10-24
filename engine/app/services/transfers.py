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
    Region,
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
    def __init__(self, svc: Services) -> None:
        self.svc = svc
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

    async def _ingest(self, t: Transfer, req: VitalsRequest) -> VitalsReading:
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
        if reading.source == VitalsSource.presage:
            t.monitoring.source = MonitoringSource.presage
            t.monitoring.hint = req.hint
        if reading.source in (VitalsSource.presage, VitalsSource.simulated):
            t.monitoring.last_reading_at = reading.recorded_at
        if reading.source == VitalsSource.manual:
            await self._note(t, Author.crew, NoteKind.event, "Vitals entered: " + describe(reading), at=reading.recorded_at)
        await self._reassess(t)
        return reading

    async def _reassess(self, t: Transfer) -> None:
        now = self.now()
        readings = await self.repo.get_vitals(t.id, 240)
        before_total = t.news2.total if t.news2 else None
        t.news2 = compute_news2(readings, now, NEWS2_LOOKBACK_MIN)
        trend = await self._trend_buckets(t, 60, readings)
        fc = forecast(trend, now, t.eta)
        before = t.alerts
        t.alerts = alerts_mod.evaluate(t.news2, t.latest, fc, before, now)
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
        buckets, source = await self.repo.vitals_trend(t.id, self.now() - timedelta(minutes=window_min))
        filled = await self._trend_buckets(t, window_min)
        return TrendResponse(buckets=filled, source=source, forecast=forecast(filled, self.now(), t.eta))  # type: ignore[arg-type]

    async def set_monitoring(self, transfer_id: UUID, source: MonitoringSource) -> Transfer:
        async with self.locks[transfer_id]:
            t = await self._load(transfer_id)
            if t.monitoring.source != source:
                t.monitoring.source = source
                t.monitoring.hint = None
                text = {
                    MonitoringSource.presage: "Contactless monitoring: Presage camera connected",
                    MonitoringSource.simulated: "Contactless monitoring: simulated (Presage bridge not connected)",
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
        except Exception:  # noqa: BLE001
            log.exception("briefing refresh failed")

    # ---------------------------------------------------------------- notes & messages
    async def _extract(self, text: str) -> tuple[Extraction, str]:
        if self.svc.gemini.status == "real":
            ge, _err = await self.svc.gemini.extract(text)
            if ge is not None:
                return Extraction(observations=ge.observations[:6], interventions=ge.interventions[:4]), "gemini"
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

    async def voice_note(self, transfer_id: UUID, audio: bytes, filename: str, content_type: str,
                         reply_to: UUID | None) -> Transfer:
        try:
            result = await self.svc.elevenlabs.transcribe(audio, filename, content_type, None)
        except Exception as exc:  # noqa: BLE001
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

            def num(field: str) -> float | None:
                lv = t.latest.get(field)
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
        return [DemoCase(**{k: v for k, v in c.items() if k in DemoCase.model_fields}) for c in regions.cases()]

    async def start_case(self, case_id: str | None = None, history_min: int = 8) -> Transfer:
        """Start a prepared case in its region: patient, complaint and route filled in, crew-entered baseline vitals,
        and `history_min` minutes of earlier contactless readings (labelled simulated) so trends are populated."""
        if case_id is None:
            region_id = self.svc.clock.state.region_id
            c = next((x for x in regions.cases() if x["region_id"] == region_id), None)
        else:
            c = regions.case(case_id)
        if c is None:
            raise AppError("no_case", "No prepared case found", 404)
        self.svc.clock.state.region_id = c["region_id"]
        await self.repo.set_demo_state(self.svc.clock.state)
        now = self.now()
        start = now - timedelta(minutes=history_min)
        t = await self.create(
            CreateTransferRequest(patient=Patient(**c["patient"]), complaint=c["complaint"], origin_id=c["origin_id"],
                                  destination_id=c["destination_id"], mode=c["mode"]),
            at=start,
        )
        profile = SimProfile(**c.get("profile", {}))
        async with self.locks[t.id]:
            cur = await self._load(t.id)
            cur.sim_profile = profile
            for i in range(0, history_min * 60, 30):
                at = start + timedelta(seconds=i)
                values = simulated_values(profile, start, at, zlib.crc32(cur.code.encode()))
                reading = VitalsReading(id=uuid4(), transfer_id=cur.id, recorded_at=at, source=VitalsSource.simulated,
                                        confidence=0.9, **values)
                await self.repo.add_vitals(reading)
                cur.latest = update_latest(cur.latest, reading)
            cur.monitoring.last_reading_at = now
            base = c.get("baseline_vitals")
            if base:
                await self._ingest(cur, VitalsRequest(source="manual", recorded_at=start + timedelta(minutes=2), **base))
            await self._reassess(cur)
            await self._save(cur)
        return await self.get(t.id)
