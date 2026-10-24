# F-M8.3 Demo scenarios: create a case, post scripted intake/vitals at scripted sim times, optionally autoplay
# refer → accept → dispatch. Steps with at_min ≤ 0 are back-dated and run immediately; later steps are run by the
# simulator loop when the sim clock reaches them (progress is stored on CaseMeta, so it survives restarts).
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from app.core import refdata
from app.models import (
    Case,
    CaseMeta,
    CaseStatus,
    CreateCaseRequest,
    DemoStatePatch,
    DispatchRequest,
    EventType,
    ManualVitalsRequest,
    Patient,
    ReferRequest,
    RespondRequest,
    WeatherPatch,
)
from app.services.context import AppError, Services

log = logging.getLogger("atollcare.scenarios")


def sorted_steps(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(scenario["steps"], key=lambda s: s["at_min"])


class ScenarioService:
    def __init__(self, svc: Services, cases, demo) -> None:
        self.svc = svc
        self.cases = cases
        self.demo = demo

    async def load(self, scenario_id: str, autoplay: bool) -> Case:
        sc = refdata.scenarios().get(scenario_id)
        if sc is None:
            raise AppError("not_found", f"Unknown scenario {scenario_id}", 404)
        weather = sc.get("weather") or {}
        await self.demo.patch(
            DemoStatePatch(set_time_of_day=sc["clock"], weather=WeatherPatch(**weather), clear_night_override=True),
            reassess=False,
        )
        now = self.svc.clock.now()
        steps = sorted_steps(sc)
        first = min(0, steps[0]["at_min"]) if steps else 0
        meta = CaseMeta(scenario_id=scenario_id, scenario_started_at=now, autoplay=autoplay)
        case = await self.cases.create(
            CreateCaseRequest(origin_facility_id=sc["origin_facility_id"], patient=Patient(**sc.get("patient", {}))),
            actor="reporter", at=now + timedelta(minutes=first), meta=meta,
        )
        await self.run_due(case.id)
        return await self.cases.get(case.id)

    async def run_due(self, case_id: UUID) -> None:
        case = await self.cases.get(case_id)
        sc = refdata.scenarios().get(case.meta.scenario_id or "")
        if sc is None or case.meta.scenario_started_at is None:
            return
        steps = sorted_steps(sc)
        done = case.meta.scenario_steps_done
        now = self.svc.clock.now()
        while done < len(steps):
            step = steps[done]
            at = case.meta.scenario_started_at + timedelta(minutes=step["at_min"])
            if at > now:
                break
            if not step.get("autoplay") or case.meta.autoplay:
                try:
                    await self._run_step(case_id, sc, step, min(at, now) if step["at_min"] <= 0 else None)
                except AppError as exc:
                    await self._note(case_id, f"Scenario step '{step['action']}' skipped: {exc.message}")
                except Exception as exc:  # noqa: BLE001
                    log.exception("scenario step failed")
                    await self._note(case_id, f"Scenario step '{step['action']}' failed: {exc}")
            done += 1
            await self._mark_done(case_id, done)

    async def _mark_done(self, case_id: UUID, done: int) -> None:
        async with self.cases.locks[case_id]:
            case = await self.cases.repo.get_case(case_id)
            if case is None:
                return
            case.meta.scenario_steps_done = done
            await self.cases.repo.update_case(case)

    async def _note(self, case_id: UUID, text: str) -> None:
        async with self.cases.locks[case_id]:
            case = await self.cases.repo.get_case(case_id)
            if case:
                await self.cases._event(case, EventType.note, "demo", text)

    async def _run_step(self, case_id: UUID, sc: dict[str, Any], step: dict[str, Any], at: datetime | None) -> None:
        action = step["action"]
        if action == "intake":
            await self.cases.intake(case_id, sc["intake_text"], None, actor="reporter", at=at)
        elif action == "vitals":
            v = dict(step["vitals"])
            await self.cases.add_vitals(case_id, ManualVitalsRequest(recorded_at=at, **v),
                                        actor="reporter" if v.get("source") == "presage" else "clinician", at=at)
        elif action == "submit":
            await self.cases.submit(case_id, actor="reporter", at=at)
        elif action == "refer":
            await self.cases.refer(case_id, ReferRequest(note=step.get("note")), actor="clinician")
        elif action == "respond":
            case = await self.cases.get(case_id)
            if case.status not in {CaseStatus.referred, CaseStatus.needs_info}:
                raise AppError("invalid_state", f"case is {case.status.value}", 409)
            await self.cases.respond(case_id, RespondRequest(
                response=step.get("response", "accepted"), responder_name=step.get("responder_name", "Specialist"),
                note=step.get("note"), info_requests=step.get("info_requests", []),
            ))
        elif action == "dispatch":
            case = await self.cases.get(case_id)
            if case.recommendation is None:
                raise AppError("invalid_state", "no recommendation", 409)
            await self.cases.dispatch(case_id, DispatchRequest(route_id=case.recommendation.chosen_route_id))
        else:
            raise AppError("unknown_step", f"unknown scenario action {action}", 422)

    async def tick(self) -> None:
        for case in await self.cases.repo.list_cases():
            sc = refdata.scenarios().get(case.meta.scenario_id or "")
            if sc is None or case.meta.scenario_steps_done >= len(sc["steps"]) or case.status == CaseStatus.closed:
                continue
            await self.run_due(case.id)
