# F-M2.7 SBAR template fallback, F-M2.9 headline metric, F-M4.8 crew brief, F-M1.8 status sentence — deterministic
# text builders. Gemini versions live in adapters/gemini.py and are layered on by the service.
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from app.core import refdata
from app.core.clock import fmt_local
from app.core.decision import fmt_min
from app.core.news2 import partial_label
from app.models import Case, CaseHeadline, SbarSummary


def _fac(fid: str | None) -> str:
    if not fid:
        return "not recorded"
    f = refdata.facility(fid)
    return f.label if f else fid


def chosen_route(case: Case):
    rec = case.recommendation
    if rec is None:
        return None
    return next((r for r in rec.alternatives if r.id == rec.chosen_route_id), None)


def condition_label(cid: str | None) -> str:
    if not cid:
        return "undifferentiated"
    spec = refdata.conditions().get(cid)
    return spec["label"] if spec else cid


def sbar_inputs(case: Case) -> dict[str, Any]:
    """Case JSON passed to Gemini (and hashed for caching). Only facts that exist on the case."""
    latest = case.news2.values_used if case.news2 else {}
    rec = case.recommendation
    route = chosen_route(case)
    return {
        "patient": case.patient.model_dump(mode="json"),
        "origin": _fac(case.origin_facility_id),
        "intake": case.intake.model_dump(mode="json", exclude={"raw_text"}) if case.intake else None,
        "reporter_text": case.intake.raw_text if case.intake else None,
        "latest_vitals": latest,
        "news2": {"total": case.news2.total, "band": case.news2.band, "complete": case.news2.complete}
        if case.news2 else None,
        "severity": rec.severity.value if rec else None,
        "primary_condition": condition_label(rec.primary_condition_id) if rec else None,
        "destination": _fac(case.referral.destination_id if case.referral else (rec.destination_id if rec else None)),
        "route": route.label if route else None,
        "route_total_min": route.total_min if route else None,
        "breach_warning": rec.breach_warning if rec else None,
        "info_answers": [a.model_dump(mode="json") for a in case.referral.info_answers] if case.referral else [],
        "referral_note": case.referral.note if case.referral else None,
    }


def inputs_hash(data: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()[:16]


def template_sbar(case: Case) -> SbarSummary:
    p = case.patient
    who = " ".join(x for x in [f"{p.age}y" if p.age else None, p.sex] if x) or "Patient"
    rec = case.recommendation
    intake = case.intake
    n2 = case.news2
    n2_txt = "NEWS2 not recorded"
    if n2 and n2.total is not None:
        n2_txt = f"NEWS2 {n2.total} ({n2.band})" + ("" if n2.complete else f" — {partial_label(n2)}")
    complaint = intake.chief_complaint if intake else "not recorded"
    situation = f"{who} at {_fac(case.origin_facility_id)}: {complaint}. "
    situation += f"Severity {rec.severity.value.replace('_', '-')}, {n2_txt}." if rec else f"{n2_txt}."
    onset = "not recorded"
    if intake and intake.onset_time:
        onset = f"{fmt_local(intake.onset_time)} ({intake.onset_confidence})"
    background = (
        f"Onset {onset}. History: {', '.join(p.known_conditions) or 'not recorded'}. "
        f"Meds: {', '.join(p.medications) or 'not recorded'}. Allergies: {', '.join(p.allergies) or 'not recorded'}."
    )
    vals = n2.values_used if n2 else {}
    vit = ", ".join(
        f"{label} {vals[k]}"
        for k, label in [("heart_rate", "HR"), ("resp_rate", "RR"), ("spo2", "SpO₂"), ("systolic_bp", "SBP"),
                         ("temperature_c", "T"), ("consciousness", "ACVPU")]
        if k in vals
    ) or "not recorded"
    flags = ", ".join(intake.red_flags) if intake and intake.red_flags else "none recorded"
    assessment = f"Suspected {condition_label(rec.primary_condition_id if rec else None).lower()}. Red flags: {flags}. Vitals: {vit}."
    route = chosen_route(case)
    dest = case.referral.destination_id if case.referral else (rec.destination_id if rec else None)
    recommendation = f"Request acceptance at {_fac(dest)}"
    if rec:
        recommendation += f" ({', '.join(rec.required_capabilities)})"
    if route:
        recommendation += f". Planned: {route.label}, ETA {fmt_min(route.total_min)}"
    recommendation += "."
    if rec and rec.breach_warning:
        recommendation += " Window breach expected — interim plan in place." if route and route.interim_stop_id else ""
    return SbarSummary(
        situation=situation, background=background, assessment=assessment, recommendation=recommendation,
        generated_by="template",
    )


def onset_of(case: Case) -> datetime:
    if case.intake and case.intake.onset_time:
        return case.intake.onset_time
    return case.created_at


def headline(case: Case, now: datetime) -> CaseHeadline:
    """Symptom → definitive care: X h Y min. Estimated Z min faster than the phone-chain baseline."""
    onset = onset_of(case)
    elapsed = max(0.0, (now - onset).total_seconds() / 60)
    rec = case.recommendation
    if rec is None:
        return CaseHeadline(
            elapsed_min=round(elapsed, 1), projected_total_min=None, saved_vs_baseline_min=None,
            text=f"Awaiting assessment — {fmt_min(elapsed)} since symptom onset.",
        )
    meta = case.meta
    base = rec.baseline
    start = meta.submitted_at or case.created_at
    if meta.arrived_at:
        total = (meta.arrived_at - onset).total_seconds() / 60
        ours = (meta.arrived_at - start).total_seconds() / 60
        saved = base.baseline_total_min - ours
        verb = "Actual"
    elif case.transport.eta and case.transport.status in ("dispatched", "in_transit"):
        total = (case.transport.eta - onset).total_seconds() / 60
        saved = base.saved_vs_baseline_min
        verb = "Projected"
    else:
        total = (start - onset).total_seconds() / 60 + base.ours_total_min
        saved = base.saved_vs_baseline_min
        verb = "Projected"
    faster = "faster" if saved >= 0 else "slower"
    text = (
        f"Symptom → definitive care: {fmt_min(total)}. "
        f"{'Estimated ' if verb == 'Projected' else ''}{fmt_min(abs(saved))} {faster} than the phone-chain baseline."
    )
    return CaseHeadline(
        elapsed_min=round(elapsed, 1), projected_total_min=round(total, 1), saved_vs_baseline_min=round(saved, 1),
        text=text,
    )


STATUS_SENTENCES = {
    "draft": "The alert is being prepared.",
    "submitted": "The alert has been sent and is being assessed.",
    "assessed": "The doctor has a recommended plan and is preparing the referral.",
    "referred": "The referral has been sent to {dest}. Waiting for the specialist to accept.",
    "needs_info": "The specialist at {dest} has asked for more information.",
    "accepted": "{dest} has accepted the patient. Transport is being arranged.",
    "declined": "The referral was declined. Another hospital is being contacted.",
    "dispatched": "Transport has been dispatched. Departure at {depart}.",
    "in_transit": "The patient is on the way to {dest}. Expected arrival {eta}.",
    "arrived": "The patient has arrived at {dest}.",
    "closed": "The case is closed.",
}


def status_sentence(case: Case, now: datetime) -> str:
    rec = case.recommendation
    dest = _fac(case.referral.destination_id if case.referral else (rec.destination_id if rec else None))
    t = case.transport
    eta = "soon"
    if t.eta:
        mins = (t.eta - now).total_seconds() / 60
        eta = f"in {fmt_min(max(0, mins))}" if mins > 0 else "any moment now"
    depart = fmt_local(t.route.legs[0].depart_at) if t.route and t.route.legs else "shortly"
    return STATUS_SENTENCES[case.status.value].format(dest=dest, eta=eta, depart=depart)


def crew_brief(case: Case) -> str:
    p = case.patient
    rec = case.recommendation
    who = " ".join(x for x in [f"{p.age}-year-old" if p.age else None, {"M": "man", "F": "woman"}.get(p.sex or "", "patient")] if x)
    n2 = case.news2
    parts = [f"Crew brief, case {case.short_code}. {who.capitalize()} from {_fac(case.origin_facility_id)}."]
    if rec:
        parts.append(f"Suspected {condition_label(rec.primary_condition_id).lower()}, severity {rec.severity.value.replace('_', ' ')}.")
    if n2 and n2.total is not None:
        parts.append(f"Latest NEWS2 {n2.total}.")
    if p.allergies:
        parts.append(f"Allergies: {', '.join(p.allergies)}.")
    route = case.transport.route or chosen_route(case)
    if route:
        parts.append(f"Plan: {route.label}.")
    if rec and rec.forecast and rec.forecast.trend == "worsening":
        parts.append("Trend suggests deterioration — monitor closely and report changes.")
    return " ".join(parts)
