# F-M2.1 orchestration + case lifecycle (F-M1.*, F-M3.*, F-M4.2/4.5). Routers call this; every mutation appends a
# CaseEvent and returns the hydrated Case. Per-case locks serialise mutations (simulator vs. user actions).
from __future__ import annotations

import asyncio
import logging
import random
import time as _time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from app.core import decision, fallback_intake, refdata, summary
from app.core.clock import fmt_local
from app.core.forecast import bucket_news2
from app.core.news2 import compute as compute_news2
from app.db import EMPTY_HEADLINE
from app.models import (
    Case,
    CaseEvent,
    CaseListItem,
    CaseMeta,
    CaseStatus,
    CloseRequest,
    CreateCaseRequest,
    DispatchRequest,
    EventType,
    GeoPoint,
    GuidanceResponse,
    GuidanceStep,
    InfoAnswer,
    InfoAnswersRequest,
    Intake,
    ManualVitalsRequest,
    PatchCaseRequest,
    Patient,
    Recommendation,
    Referral,
    ReferRequest,
    RespondRequest,
    RouteOption,
    SbarSummary,
    SuspectedCondition,
    TrackResponse,
    TransportState,
    TrendBucket,
    TrendResponse,
    VitalsReading,
)
from app.services.context import AppError, Services

log = logging.getLogger("atollcare.cases")
OPEN_STATUSES = {
    CaseStatus.submitted, CaseStatus.assessed, CaseStatus.referred, CaseStatus.needs_info, CaseStatus.accepted,
    CaseStatus.declined,
}
REFERRAL_STATUSES = {CaseStatus.referred, CaseStatus.needs_info, CaseStatus.accepted}
DEBOUNCE_S = 2.0
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
VITAL_LABELS = [("heart_rate", "HR"), ("resp_rate", "RR"), ("spo2", "SpO₂"), ("systolic_bp", "SBP"),
                ("temperature_c", "T"), ("consciousness", "ACVPU")]


class CaseService:
    def __init__(self, svc: Services) -> None:
        self.svc = svc
        self.repo = svc.repo
        self.locks: dict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_assess: dict[UUID, float] = {}
        self._pending: dict[UUID, asyncio.Task] = {}

    # ---------------------------------------------------------------- helpers
    def now(self) -> datetime:
        return self.svc.clock.now()

    async def _load(self, case_id: UUID) -> Case:
        case = await self.repo.get_case(case_id)
        if case is None:
            raise AppError("not_found", f"Case {case_id} not found", 404)
        return case

    async def _save(self, case: Case, at: datetime | None = None) -> None:
        case.updated_at = at or self.now()
        await self.repo.update_case(case)

    async def _event(
        self, case: Case, etype: EventType, actor: str, text: str, data: dict[str, Any] | None = None,
        at: datetime | None = None,
    ) -> CaseEvent:
        ev = CaseEvent(id=uuid4(), case_id=case.id, at=at or self.now(), type=etype, actor_role=actor, summary=text,
                       data=data or {})
        await self.repo.add_event(ev)
        case.timeline.append(ev)
        return ev

    def hydrate(self, case: Case) -> Case:
        case.headline = summary.headline(case, self.now())
        return case

    async def get(self, case_id: UUID) -> Case:
        return self.hydrate(await self._load(case_id))

    def _fac_label(self, fid: str | None) -> str:
        f = refdata.facility(fid) if fid else None
        return f.label if f else (fid or "—")

    async def _short_code(self) -> str:
        existing = {c.short_code for c in await self.repo.list_cases()}
        while True:
            code = "AC-" + "".join(random.choices(CODE_ALPHABET, k=4))
            if code not in existing:
                return code

    # ---------------------------------------------------------------- world context
    async def trend(self, case_id: UUID, window_min: int = 60, at: datetime | None = None) -> TrendResponse:
        now = at or self.now()
        buckets, source = await self.repo.vitals_trend(case_id, now - timedelta(minutes=window_min))
        vitals = await self.repo.get_vitals(case_id, 50)
        extra: dict[str, Any] = {}
        for r in reversed(vitals):  # non-aggregated params from the latest raw reading
            if r.consciousness is not None and "consciousness" not in extra:
                extra["consciousness"] = r.consciousness.value
            if r.on_oxygen is not None and "on_oxygen" not in extra:
                extra["on_oxygen"] = r.on_oxygen
        return TrendResponse(buckets=bucket_news2(buckets, extra), source=source)  # type: ignore[arg-type]

    async def _assess_context(self, case: Case, trend: list[TrendBucket]) -> decision.AssessContext:
        st = self.svc.clock.state
        caps = {c.facility_id: c for c in await self.repo.list_capacity()}
        declined = set(case.referral.declined_destination_ids) if case.referral else set()
        pin = None
        if case.referral and case.referral.response != "declined" and case.status in REFERRAL_STATUSES:
            pin = case.referral.destination_id
        return decision.AssessContext(
            now=self.now(),
            weather=st.weather,
            night_override=st.night_override,
            helicopter_enabled=st.helicopter_enabled,
            assets=await self.repo.list_assets(),
            capacity=caps,
            trend=trend,
            declined=declined,
            pin_destination=pin,
        )

    async def compute_routes(self, case: Case) -> list[RouteOption]:
        trend = (await self.trend(case.id)).buckets
        return decision.assess(case, await self._assess_context(case, trend)).routes

    # ---------------------------------------------------------------- assessment (F-M2.1)
    async def _assess(
        self, case: Case, actor: str = "system", reason: str | None = None, handle_replan: bool = True
    ) -> None:
        """Run the engine on a case (lock held). Handles explanation caching, re-plans and referral re-send."""
        self._last_assess[case.id] = _time.monotonic()
        trend = (await self.trend(case.id)).buckets
        res = decision.assess(case, await self._assess_context(case, trend))
        rec = res.recommendation
        prev = case.recommendation
        await self._explain(case, rec, prev)
        case.news2 = res.news2  # type: ignore[assignment]
        case.recommendation = rec
        case.meta.last_assessed_at = self.now()
        if case.status == CaseStatus.submitted:
            case.status = CaseStatus.assessed
        changed_dest = prev is not None and prev.destination_id != rec.destination_id
        changed_route = prev is not None and prev.chosen_route_id != rec.chosen_route_id
        route = summary.chosen_route(case)
        if prev is None or changed_dest or changed_route:
            await self._event(
                case, EventType.assessed, actor,
                f"Assessed: {rec.severity.value.replace('_', '-')} · {summary.condition_label(rec.primary_condition_id)}"
                f" → {self._fac_label(rec.destination_id)} via {route.label if route else '—'} "
                f"({decision.fmt_min(route.total_min if route else None)})",
                {"destination_id": rec.destination_id, "route_id": rec.chosen_route_id, "reason": reason},
            )
        if changed_dest and prev is not None and handle_replan:
            await self._handle_replan(case, prev, reason)

    async def _handle_replan(self, case: Case, prev: Recommendation, reason: str | None) -> None:
        rec = case.recommendation
        assert rec is not None
        why = reason or "conditions changed"
        if case.referral and case.status in REFERRAL_STATUSES:
            why = self._exclusion_reason(rec, case.referral.destination_id) or why
            old = case.referral
            case.referral = Referral(
                destination_id=rec.destination_id, sent_at=self.now(), note=old.note,
                declined_destination_ids=old.declined_destination_ids, info_answers=old.info_answers,
            )
            case.status = CaseStatus.referred
            case.meta.accepted_at = None
            case.referral.sbar = await self._sbar(case)
            text = f"Re-routed to {self._fac_label(rec.destination_id)}: {why}. Referral re-sent automatically."
        else:
            text = f"Re-planned to {self._fac_label(rec.destination_id)}: {why}."
        await self._event(case, EventType.replanned, "system", text,
                          {"from": prev.destination_id, "to": rec.destination_id, "toast": True})

    def _exclusion_reason(self, rec: Recommendation, old_dest: str) -> str | None:
        name = self._fac_label(old_dest)
        for w in rec.warnings:
            for part in w.removeprefix("Excluded: ").split("; "):
                if part.startswith(refdata.facility(old_dest).name if refdata.facility(old_dest) else old_dest):
                    return f"{name} {part.split(': ', 1)[-1]}"
        return None

    async def _explain(self, case: Case, rec: Recommendation, prev: Recommendation | None) -> None:
        if prev and prev.input_hash == rec.input_hash and prev.explanation_source == "gemini":
            rec.explanation, rec.explanation_source = prev.explanation, "gemini"
            return
        if self.svc.gemini.status != "real":
            return
        payload = {
            "chosen": rec.chosen_route_id,
            "time_since_window_start_min": rec.time_since_onset_min,
            "window_min": rec.window_min,
            "breach_warning": rec.breach_warning,
            "routes": [
                {"id": r.id, "label": r.label, "total_min": r.total_min, "feasible": r.feasible,
                 "infeasible_reasons": r.infeasible_reasons, "within_window": r.within_window,
                 "interim_stop": r.interim_stop_id, "medic_onboard": r.medic_onboard}
                for r in rec.alternatives
            ],
            "rejected_examples": [],
        }
        text, err = await self.svc.gemini.explain(payload)
        if text:
            rec.explanation, rec.explanation_source = text, "gemini"
        elif err and (prev is None or prev.input_hash != rec.input_hash):
            await self._event(case, EventType.note, "system", f"{err} — used template route explanation.")

    async def assess(self, case_id: UUID, actor: str = "clinician", reason: str | None = None) -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status == CaseStatus.draft:
                raise AppError("invalid_state", "Submit the case before assessing", 409)
            await self._assess(case, actor, reason or "manual re-assessment")
            await self._save(case)
        return await self.get(case_id)

    async def _reassess_one(self, case_id: UUID, reason: str) -> None:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status not in OPEN_STATUSES:
                return
            await self._assess(case, "system", reason)
            await self._save(case)

    async def reassess_open(self, reason: str) -> None:
        """Broadcast re-assessment (capacity / asset / demo-state changes) with a per-case 2 s debounce."""
        for case in await self.repo.list_cases():
            if case.status not in OPEN_STATUSES:
                continue
            since = _time.monotonic() - self._last_assess.get(case.id, 0)
            if since >= DEBOUNCE_S:
                await self._reassess_one(case.id, reason)
                continue
            if case.id in self._pending and not self._pending[case.id].done():
                continue
            self._pending[case.id] = asyncio.create_task(self._delayed(case.id, reason, DEBOUNCE_S - since))

    async def _delayed(self, case_id: UUID, reason: str, delay: float) -> None:
        await asyncio.sleep(delay)
        try:
            await self._reassess_one(case_id, reason)
        except Exception:  # noqa: BLE001
            log.exception("debounced re-assessment failed for %s", case_id)

    # ---------------------------------------------------------------- creation & intake (F-M1.1–1.5)
    async def create(self, req: CreateCaseRequest, actor: str = "reporter", at: datetime | None = None,
                     meta: CaseMeta | None = None) -> Case:
        origin = refdata.facility(req.origin_facility_id)
        if origin is None or origin.type == "airport":
            raise AppError("invalid_origin", f"Unknown origin facility {req.origin_facility_id}", 422)
        now = at or self.now()
        case = Case(
            id=uuid4(),
            short_code=await self._short_code(),
            created_at=now,
            updated_at=now,
            status=CaseStatus.draft,
            origin_facility_id=origin.id,
            origin_point=GeoPoint(lat=origin.lat, lng=origin.lng),
            patient=req.patient or Patient(),
            transport=TransportState(),
            headline=EMPTY_HEADLINE,
            meta=meta or CaseMeta(),
        )
        await self.repo.insert_case(case)
        await self._event(case, EventType.created, actor, f"Alert raised at {origin.label} ({case.short_code})", at=now)
        if req.raw_text:
            async with self.locks[case.id]:
                await self._intake(case, req.raw_text, None, actor, at=now)
                await self._save(case, now)
        return await self.get(case.id)

    async def patch(self, case_id: UUID, req: PatchCaseRequest, actor: str = "clinician") -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            changes: list[str] = []
            if req.patient is not None:
                case.patient = req.patient
                changes.append("patient details")
            if req.origin_facility_id and req.origin_facility_id != case.origin_facility_id:
                origin = refdata.facility(req.origin_facility_id)
                if origin is None or origin.type == "airport":
                    raise AppError("invalid_origin", "Unknown origin facility", 422)
                case.origin_facility_id = origin.id
                case.origin_point = GeoPoint(lat=origin.lat, lng=origin.lng)
                changes.append(f"origin → {origin.label}")
            if changes:
                await self._event(case, EventType.note, actor, "Updated " + ", ".join(changes))
                if case.status in OPEN_STATUSES:
                    await self._assess(case, actor, "case details changed")
                if case.referral and case.status in REFERRAL_STATUSES:
                    case.referral.sbar = await self._sbar(case)
                await self._save(case)
        return await self.get(case_id)

    async def _intake(self, case: Case, raw_text: str, language: str | None, actor: str,
                      at: datetime | None = None) -> None:
        now = at or self.now()
        origin = refdata.facility(case.origin_facility_id)
        intake: Intake | None = None
        if self.svc.gemini.status == "real":
            gi, err = await self.svc.gemini.extract_intake(
                raw_text, now, [c for c in refdata.conditions() if c != "other"],
                {"origin": origin.name if origin else case.origin_facility_id,
                 "patient": case.patient.model_dump(mode="json")},
            )
            if gi is not None:
                onset = None
                if gi.onset_time:
                    try:
                        onset = datetime.fromisoformat(gi.onset_time.replace("Z", "+00:00"))
                        if onset.tzinfo is None:
                            onset = onset.replace(tzinfo=now.tzinfo)
                    except ValueError:
                        onset = None
                intake = Intake(
                    raw_text=raw_text, language=gi.language or language or "en",
                    chief_complaint=gi.chief_complaint, symptoms=gi.symptoms, red_flags=gi.red_flags,
                    onset_time=onset, onset_confidence=gi.onset_confidence if onset else "unknown",
                    suspected_conditions=[
                        SuspectedCondition(condition_id=s.condition_id, probability=max(0, min(1, s.probability)),
                                           rationale=s.rationale)
                        for s in gi.suspected_conditions
                    ],
                    missing_info=gi.missing_info[:4], extracted_by="gemini",
                )
            else:
                await self._event(case, EventType.note, "system", f"{err} — used rule-based intake.", at=now)
        if intake is None:
            intake = fallback_intake.extract(raw_text, now, language or "en")
        case.intake = intake
        case.meta.language = intake.language
        top = intake.suspected_conditions[0] if intake.suspected_conditions else None
        await self._event(
            case, EventType.intake_extracted, actor,
            f"Intake ({'Gemini' if intake.extracted_by == 'gemini' else 'rule-based'}): {intake.chief_complaint}"
            + (f" — suspected {summary.condition_label(top.condition_id)} ({top.probability:.0%})" if top else ""),
            {"extracted_by": intake.extracted_by, "red_flags": intake.red_flags},
            at=now,
        )

    async def intake(self, case_id: UUID, raw_text: str, language: str | None, actor: str = "reporter",
                     at: datetime | None = None) -> Case:
        if not raw_text.strip():
            raise AppError("empty_text", "Describe what is happening first", 422)
        async with self.locks[case_id]:
            case = await self._load(case_id)
            await self._intake(case, raw_text, language, actor, at)
            if case.status in OPEN_STATUSES:
                await self._assess(case, actor, "new intake")
            await self._save(case, at)
        return await self.get(case_id)

    async def submit(self, case_id: UUID, actor: str = "reporter", at: datetime | None = None) -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status != CaseStatus.draft:
                return self.hydrate(case)
            now = at or self.now()
            case.status = CaseStatus.submitted
            case.meta.submitted_at = now
            await self._event(case, EventType.submitted, actor, "Alert submitted to the health centre / doctor", at=now)
            if case.intake is None:
                await self._intake(case, "Unwell — no description provided", None, "system", at=now)
            await self._assess(case, "system", "submitted")
            await self._save(case, now)
        return await self.get(case_id)

    # ---------------------------------------------------------------- vitals (F-M1.4, F-M6.*)
    async def _add_reading(self, case: Case, reading: VitalsReading, actor: str) -> None:
        await self.repo.add_vitals(reading)
        case.vitals.append(reading)
        parts: list[str] = []
        for key, label in VITAL_LABELS:
            value = getattr(reading, key)
            if value is None:
                continue
            parts.append(f"{label} {value.value if hasattr(value, 'value') else f'{value:g}'}")
        src = {"presage": "Presage scan", "mock": "Camera scan (mock)", "manual": "Manual", "device": "Device"}
        text = f"{src.get(reading.source.value, reading.source.value)}: {', '.join(parts) or 'no values'}"
        if reading.confidence is not None:
            text += f" (confidence {reading.confidence:.2f})"
        if reading.low_quality:
            text += " — low quality, excluded from NEWS2; please rescan"
        await self._event(case, EventType.vitals_added, actor, text, {"reading_id": str(reading.id)},
                          at=reading.recorded_at)

    async def add_vitals(self, case_id: UUID, req: ManualVitalsRequest, actor: str = "clinician",
                         at: datetime | None = None) -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status == CaseStatus.closed:
                raise AppError("invalid_state", "Case is closed", 409)
            now = at or self.now()
            data = req.model_dump()
            recorded = data.pop("recorded_at") or now
            conf = data.get("confidence")
            reading = VitalsReading(id=uuid4(), case_id=case.id, recorded_at=recorded,
                                    low_quality=conf is not None and conf < 0.6, **data)
            await self._add_reading(case, reading, actor)
            case.news2 = compute_news2(case.vitals, now)
            if case.status in OPEN_STATUSES:
                await self._assess(case, actor, "new vitals")
            await self._save(case, now)
        return await self.get(case_id)

    # ---------------------------------------------------------------- referral (F-M1.6, F-M3.3–3.5)
    async def _sbar(self, case: Case) -> SbarSummary:
        inputs = summary.sbar_inputs(case)
        h = summary.inputs_hash(inputs)
        old = case.referral.sbar if case.referral else None
        if old and old.input_hash == h:
            return old
        if self.svc.gemini.status == "real":
            gs, err = await self.svc.gemini.sbar(inputs)
            if gs is not None:
                return SbarSummary(**gs.model_dump(), generated_by="gemini", input_hash=h)
            await self._event(case, EventType.note, "system", f"{err} — used template SBAR.")
        sb = summary.template_sbar(case)
        sb.input_hash = h
        return sb

    async def sbar_preview(self, case_id: UUID) -> SbarSummary:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            return await self._sbar(case)

    async def refer(self, case_id: UUID, req: ReferRequest, actor: str = "clinician") -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status not in OPEN_STATUSES or case.recommendation is None:
                raise AppError("invalid_state", f"Cannot refer a case in status {case.status.value}", 409)
            dest = req.destination_id or case.recommendation.destination_id
            fac = refdata.facility(dest)
            if fac is None or not set(case.recommendation.required_capabilities) <= set(fac.capabilities):
                raise AppError("incapable_destination", f"{dest} lacks the required capabilities", 422)
            declined = case.referral.declined_destination_ids if case.referral else []
            case.referral = Referral(destination_id=dest, sent_at=self.now(), note=req.note, route_id=req.route_id,
                                     declined_destination_ids=declined)
            case.status = CaseStatus.referred
            case.meta.referred_at = self.now()
            await self._assess(case, actor, "referral sent")  # pins the destination, refreshes routes
            if case.recommendation and case.recommendation.destination_id != dest:
                raise AppError("unreachable_destination", f"No route to {fac.label} under current conditions", 409)
            case.referral.sbar = await self._sbar(case)
            await self._event(case, EventType.referred, actor, f"Referral sent to {fac.label}"
                              + (f" — note: {req.note}" if req.note else ""), {"destination_id": dest})
            await self._save(case)
        return await self.get(case_id)

    async def respond(self, case_id: UUID, req: RespondRequest) -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.referral is None or case.status not in {CaseStatus.referred, CaseStatus.needs_info}:
                raise AppError("invalid_state", "No pending referral to respond to", 409)
            now = self.now()
            ref = case.referral
            ref.responded_at, ref.responder_name, ref.response_note = now, req.responder_name, req.note
            dest_label = self._fac_label(ref.destination_id)
            if req.response == "accepted":
                ref.response = "accepted"
                case.status = CaseStatus.accepted
                case.meta.accepted_at = now
                await self._event(case, EventType.accepted, "specialist",
                                  f"Accepted at {dest_label} by {req.responder_name}" + (f": {req.note}" if req.note else ""))
                await self._assess(case, "system", "accepted")  # baseline now uses measured coordination time
            elif req.response == "needs_info":
                questions = [q for q in req.info_requests if q.strip()]
                if not questions:
                    raise AppError("missing_questions", "Add at least one question", 422)
                ref.response = "needs_info"
                ref.info_requests = questions
                case.status = CaseStatus.needs_info
                await self._event(case, EventType.needs_info, "specialist",
                                  f"{req.responder_name} ({dest_label}) requested info: " + "; ".join(questions))
            else:
                if not (req.note or "").strip():
                    raise AppError("missing_reason", "A reason is required to decline", 422)
                ref.response = "declined"
                ref.declined_destination_ids = list(dict.fromkeys(ref.declined_destination_ids + [ref.destination_id]))
                case.status = CaseStatus.declined
                await self._event(case, EventType.declined, "specialist",
                                  f"Declined by {req.responder_name} ({dest_label}): {req.note}")
                prev = case.recommendation
                await self._assess(case, "system", f"{dest_label} declined", handle_replan=False)
                rec = case.recommendation
                assert rec is not None
                old_dest = ref.destination_id
                case.referral = Referral(
                    destination_id=rec.destination_id, sent_at=now, note=ref.note,
                    declined_destination_ids=ref.declined_destination_ids, info_answers=ref.info_answers,
                )
                case.status = CaseStatus.referred
                case.referral.sbar = await self._sbar(case)
                if prev is None or rec.destination_id != old_dest:
                    await self._event(
                        case, EventType.replanned, "system",
                        f"Re-routed to {self._fac_label(rec.destination_id)}: {dest_label} declined ({req.note}). "
                        f"Referral re-sent automatically.",
                        {"from": old_dest, "to": rec.destination_id, "toast": True},
                    )
            await self._save(case)
        return await self.get(case_id)

    async def provide_info(self, case_id: UUID, req: InfoAnswersRequest, actor: str = "clinician") -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.referral is None:
                raise AppError("invalid_state", "No referral on this case", 409)
            now = self.now()
            answers = [InfoAnswer(question=q, answer=a, at=now) for q, a in req.answers.items() if a.strip()]
            if not answers:
                raise AppError("empty_answers", "Provide at least one answer", 422)
            case.referral.info_answers += answers
            case.referral.info_requests = [q for q in case.referral.info_requests if q not in req.answers]
            if case.status == CaseStatus.needs_info:
                case.status = CaseStatus.referred
                case.referral.response = "pending"
            await self._event(case, EventType.info_provided, actor,
                              "Info provided: " + "; ".join(f"{a.question} → {a.answer}" for a in answers))
            case.referral.sbar = await self._sbar(case)
            await self._save(case)
        return await self.get(case_id)

    # ---------------------------------------------------------------- transport (F-M4.2, F-M4.5)
    async def dispatch(self, case_id: UUID, req: DispatchRequest, actor: str = "transport") -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status != CaseStatus.accepted:
                raise AppError("invalid_state", "Only accepted cases can be dispatched", 409)
            routes = await self.compute_routes(case)
            route = next((r for r in routes if r.id == req.route_id), None)
            if route is None:
                raise AppError("unknown_route", "Route no longer available — refresh and pick again", 409)
            if not route.feasible:
                raise AppError("infeasible_route", "Route infeasible: " + "; ".join(route.infeasible_reasons), 409)
            assets = {a.id: a for a in await self.repo.list_assets()}
            if req.asset_ids:
                needed = [leg for leg in route.legs if leg.asset_id]
                overrides = [a for a in req.asset_ids if a]
                for leg in needed:
                    match = next((assets[a] for a in overrides if a in assets and assets[a].mode == leg.mode), None)
                    if match is not None:
                        if match.status != "available":
                            raise AppError("asset_unavailable", f"{match.id} is {match.status}", 409)
                        leg.asset_id = match.id
            asset_ids = list(dict.fromkeys(leg.asset_id for leg in route.legs if leg.asset_id))
            for aid in asset_ids:
                a = assets.get(aid)
                if a is None or a.status != "available":
                    raise AppError("asset_unavailable", f"{aid} is not available", 409)
            for aid in asset_ids:
                a = assets[aid]
                a.status = "busy"
                await self.repo.upsert_asset(a)
            now = self.now()
            case.transport = TransportState(
                route_id=route.id, status="dispatched", current_leg_index=0 if route.legs else None,
                position=route.legs[0].from_point if route.legs else case.origin_point,
                eta=route.arrive_at, asset_ids=asset_ids, route=route, dispatched_at=now,
            )
            case.status = CaseStatus.dispatched
            case.meta.dispatched_at = now
            first = route.legs[0].depart_at if route.legs else now
            await self._event(
                case, EventType.dispatched, actor,
                f"Dispatched: {route.label}. Assets: {', '.join(asset_ids) or 'none'}. "
                f"First departure {fmt_local(first)}, ETA {fmt_local(route.arrive_at)}",
                {"route_id": route.id, "asset_ids": asset_ids},
            )
            await self._save(case)
        await self.svc_asset_changed()
        return await self.get(case_id)

    async def svc_asset_changed(self) -> None:
        await self.reassess_open("transport asset availability changed")

    async def _complete_arrival(self, case: Case, at: datetime, manual: bool) -> None:
        case.transport.status = "arrived"
        if case.transport.route and case.transport.route.legs:
            last = case.transport.route.legs[-1]
            case.transport.position = last.to_point
            case.transport.current_leg_index = len(case.transport.route.legs) - 1
        case.transport.legs_completed = len(case.transport.route.legs) if case.transport.route else 0
        case.status = CaseStatus.arrived
        case.meta.arrived_at = at
        dest = self._fac_label(case.transport.route.destination_id if case.transport.route else None)
        await self._event(case, EventType.arrived, "transport" if manual else "system",
                          f"Arrived at {dest}" + (" (marked manually)" if manual else "") + " — handover to receiving team",
                          at=at)
        for aid in case.transport.asset_ids:
            for a in await self.repo.list_assets():
                if a.id == aid and a.status == "busy":
                    a.status = "available"
                    await self.repo.upsert_asset(a)

    async def arrive(self, case_id: UUID) -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status not in {CaseStatus.dispatched, CaseStatus.in_transit, CaseStatus.accepted}:
                raise AppError("invalid_state", f"Cannot mark arrived from {case.status.value}", 409)
            await self._complete_arrival(case, self.now(), manual=True)
            await self._save(case)
        return await self.get(case_id)

    async def close(self, case_id: UUID, req: CloseRequest, actor: str = "specialist") -> Case:
        async with self.locks[case_id]:
            case = await self._load(case_id)
            if case.status == CaseStatus.closed:
                return self.hydrate(case)
            now = self.now()
            for aid in case.transport.asset_ids:
                for a in await self.repo.list_assets():
                    if a.id == aid and a.status == "busy":
                        a.status = "available"
                        await self.repo.upsert_asset(a)
            case.status = CaseStatus.closed
            case.meta.closed_at = now
            case.meta.outcome_note = req.outcome_note or None
            h = summary.headline(case, now)
            await self._event(case, EventType.closed, actor,
                              f"Closed{': ' + req.outcome_note if req.outcome_note else ''}. {h.text}")
            await self._save(case)
        return await self.get(case_id)

    async def add_note(self, case_id: UUID, text: str, actor: str) -> Case:
        if not text.strip():
            raise AppError("empty_note", "Note is empty", 422)
        async with self.locks[case_id]:
            case = await self._load(case_id)
            await self._event(case, EventType.note, actor, text.strip())
            await self._save(case)
        return await self.get(case_id)

    async def track(self, case_id: UUID) -> TrackResponse:
        case = await self._load(case_id)
        return TrackResponse(positions=await self.repo.get_positions(case_id), transport=case.transport)

    # ---------------------------------------------------------------- listing (F-M3.1)
    def list_item(self, case: Case) -> CaseListItem:
        now = self.now()
        rec = case.recommendation
        route = summary.chosen_route(case)
        dest = case.referral.destination_id if case.referral else (rec.destination_id if rec else None)
        since = None
        remaining = None
        if rec and rec.time_since_onset_min is not None:
            since = rec.time_since_onset_min + (now - rec.generated_at).total_seconds() / 60
            if rec.window_min is not None:
                remaining = round(rec.window_min - since, 1)
        eta = case.transport.eta or (route.arrive_at if route else None)
        return CaseListItem(
            id=case.id, short_code=case.short_code, status=case.status, severity=rec.severity if rec else None,
            origin_facility_id=case.origin_facility_id, destination_id=dest,
            primary_condition_id=rec.primary_condition_id if rec else None, window_min=rec.window_min if rec else None,
            window_remaining_min=remaining, time_since_onset_min=round(since, 1) if since is not None else None,
            eta=eta, headline=summary.headline(case, now), created_at=case.created_at, updated_at=case.updated_at,
        )

    async def list(self, status: str | None, destination_id: str | None, origin_id: str | None) -> list[CaseListItem]:
        statuses = {s.strip() for s in status.split(",")} if status else None
        items: list[CaseListItem] = []
        for case in await self.repo.list_cases():
            if statuses and case.status.value not in statuses:
                continue
            if origin_id and case.origin_facility_id != origin_id:
                continue
            item = self.list_item(case)
            if destination_id and item.destination_id != destination_id:
                continue
            items.append(item)
        order = ["critical", "high", "medium", "low_medium", "low"]
        return sorted(
            items,
            key=lambda i: (order.index(i.severity.value) if i.severity else 9,
                           i.window_remaining_min if i.window_remaining_min is not None else 1e9),
        )

    # ---------------------------------------------------------------- guidance (F-M5.3, F-M1.7)
    async def guidance(self, case_id: UUID, role: str) -> GuidanceResponse:
        case = await self._load(case_id)
        cid = case.recommendation.primary_condition_id if case.recommendation else None
        if cid is None and case.intake and case.intake.suspected_conditions:
            cid = case.intake.suspected_conditions[0].condition_id
        cid = cid if cid in refdata.conditions() else "other"
        lib = refdata.first_aid()
        role_key = "clinician" if role == "clinician" else "reporter"
        steps = (lib["conditions"].get(cid) or lib["conditions"]["other"]).get(role_key, [])
        steps = steps + [s for s in lib["common"].get(role_key, []) if s["id"] not in {x["id"] for x in steps}]
        cache_key = f"{case_id}:{cid}:{role_key}"
        selected_by = "default_order"
        ids = [s["id"] for s in steps][:6]
        if self.svc.gemini.status == "real":
            cached = self.svc.guidance_cache.get(cache_key)
            if cached:
                ids, selected_by = cached, "gemini"
            else:
                chosen, _err = await self.svc.gemini.select_guidance(
                    cid, role_key, [{"id": s["id"], "text": s["text"]} for s in steps],
                    {"chief_complaint": case.intake.chief_complaint if case.intake else None,
                     "red_flags": case.intake.red_flags if case.intake else [], "patient": case.patient.model_dump()},
                )
                if chosen:
                    ids, selected_by = chosen[:6], "gemini"
                    self.svc.guidance_cache[cache_key] = ids
        by_id = {s["id"]: s["text"] for s in steps}
        return GuidanceResponse(
            steps=[GuidanceStep(id=i, text=by_id[i]) for i in ids if i in by_id],
            source_condition_id=cid, disclaimer=lib["disclaimer"], role=role_key,  # type: ignore[arg-type]
            selected_by=selected_by,  # type: ignore[arg-type]
        )

