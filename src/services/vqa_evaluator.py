"""Step 2 of the visual cue session: look at the video and report what is actually visible.

Frames sampled from the video go to a Gemini vision model together with the cue questions chosen by
the planner. The model is deliberately NOT given the bystander's account, so it cannot be nudged into
"seeing" what it was told to expect.

Grounding is enforced here, not trusted to the model:
- a finding can only be 'present' if it cites at least one real frame; otherwise it becomes 'cannot_assess';
- cited frame numbers that do not exist are dropped;
- a cue the model forgot to answer becomes 'cannot_assess'.
evaluate_visual_cues() never raises: failures come back as 'cannot_assess' with the reason.
"""
import time
from typing import Literal

from pydantic import BaseModel

from src import config
from src.models.schemas import CueFinding, CuePlan, FrameInfo, NeurologicalCues, PlannedCue, VisualCueReport
from src.services.cue_planner import _everything, _norm, load_catalogue, plan_cues
from src.services.gemini_client import make_client
from src.services.video_prep import Frame, sample_frames

MAX_EVIDENCE_FRAMES = 4

FRAME_RULES = """- finding: "present" only if you can point to specific frames that show it; "absent" if the relevant body part
  is clearly visible and looks normal for that sign; otherwise "cannot_assess" (body part out of frame, too
  dark, blurry, hidden, or you are unsure). When in doubt choose "cannot_assess". Never guess.
- confidence: 0 to 1.
- reason: one sentence describing what you see (not what you expect).
- evidence_frames: the frame numbers that show it (required for "present").

The frames are stills sampled seconds apart: describe only what a frame shows (posture, expression, mouth,
colour). Do not claim a speed, rate, duration or movement unless it is visible by comparing frames.
Do not diagnose. Do not assume anything about the person's condition."""

PROMPT = """You are checking still frames from one video of a person, for specific visible signs.
The frames are in time order and labelled "Frame N". Judge ONLY what you can literally see.

For each sign below return:
""" + FRAME_RULES + """

Signs to check:
{cues}"""

ONE_PASS_PROMPT = """You are checking still frames from one video of a person, for specific visible signs.
The frames are in time order and labelled "Frame N". A bystander's written account of the person is also given.

For EVERY sign in the list below, give one answer made of two separate and independent parts:

PART A, from the account text only:
- mentioned_in_account: true if the account mentions this sign, otherwise false.
- account_quote: the exact words copied from the account that mention it, otherwise null.

PART B, from the frames only:
""" + FRAME_RULES + """

Part B must be judged from the frames alone. The account is unverified and may be wrong or exaggerated, and it
must NOT influence Part B: a sign the account mentions can be "absent" or "cannot_assess", and a sign the account
does not mention can be "present". If no account was given, mentioned_in_account is false for every sign.

Patient age: {age}

The bystander's account:
\"\"\"
{account}
\"\"\"

Signs to check (answer every one, exactly once):
{cues}"""


class _RawFinding(BaseModel):
    cue_id: str
    finding: Literal["present", "absent", "cannot_assess"]
    confidence: float = 0.0
    reason: str = ""
    evidence_frames: list[int] = []


class _RawInspection(BaseModel):
    findings: list[_RawFinding] = []


class _OnePassFinding(_RawFinding):
    """One sign, answered in two independent parts: A (account text) and B (frames)."""

    mentioned_in_account: bool = False
    account_quote: str | None = None


class _OnePassInspection(BaseModel):
    findings: list[_OnePassFinding] = []


def evaluate_visual_cues(video_bytes: bytes, plan: CuePlan) -> tuple[VisualCueReport, list[Frame]]:
    """Inspect a video for the planned cues. Returns the report and the sampled frames. Never raises."""
    started = time.time()
    try:
        frames = sample_frames(video_bytes, config.VQA_FRAME_INTERVAL_S, config.VQA_MAX_FRAMES)
        if not config.GEMINI_API_KEY:
            raise RuntimeError("No GEMINI_API_KEY in inputs/.env, so the video could not be inspected.")
        raw = _inspect(frames, plan)
    except Exception as exc:
        report = build_report(plan, _RawInspection(), [])
        report.issues.insert(0, f"inspection_failed: {exc.__class__.__name__}: {str(exc)[:300]}")
        return report, []
    report = build_report(plan, raw, frames)
    report.diagnostics = {"mode": "two_step", "model": config.GEMINI_VQA_MODEL, "frames_sent": len(frames),
                          "frame_interval_s": config.VQA_FRAME_INTERVAL_S, "seconds": round(time.time() - started, 1)}
    return report, frames


def run_visual_cue_session(video_bytes: bytes, transcript: str, age: int | None = None) -> tuple[VisualCueReport, list[Frame]]:
    """The whole visual cue session, never raises. VQA_MODE in inputs/.env picks one request or two."""
    if config.VQA_MODE == "one_pass":
        return evaluate_one_pass(video_bytes, transcript, age)
    return evaluate_visual_cues(video_bytes, plan_cues(transcript, age))


def evaluate_one_pass(video_bytes: bytes, transcript: str, age: int | None = None) -> tuple[VisualCueReport, list[Frame]]:
    """ONE request: frames + account + every catalogue sign, each answered separately. Never raises."""
    started = time.time()
    catalogue = load_catalogue()
    try:
        frames = sample_frames(video_bytes, config.VQA_FRAME_INTERVAL_S, config.VQA_MAX_FRAMES)
        if not config.GEMINI_API_KEY:
            raise RuntimeError("No GEMINI_API_KEY in inputs/.env, so the video could not be inspected.")
        raw = _inspect_one_pass(frames, transcript, age, catalogue)
    except Exception as exc:
        report = build_report(CuePlan(cues=_everything(catalogue)), _RawInspection(), [])
        report.issues.insert(0, f"inspection_failed: {exc.__class__.__name__}: {str(exc)[:300]}")
        return report, []
    plan = plan_from_mentions(raw, transcript, catalogue)
    report = build_report(plan, _RawInspection(findings=[_RawFinding(**f.model_dump(exclude={"mentioned_in_account", "account_quote"}))
                                                         for f in raw.findings]), frames)
    report.diagnostics = {"mode": "one_pass", "model": config.GEMINI_VQA_MODEL, "frames_sent": len(frames),
                          "frame_interval_s": config.VQA_FRAME_INTERVAL_S, "seconds": round(time.time() - started, 1)}
    return report, frames


def _inspect_one_pass(frames: list[Frame], transcript: str, age: int | None, catalogue: dict[str, dict]) -> _OnePassInspection:
    from google.genai import types

    cues = "\n".join(f"- {cid}: {c['question']} (needs: {c['needs']})" for cid, c in catalogue.items())
    contents: list = [ONE_PASS_PROMPT.format(cues=cues, age=age if age is not None else "unknown",
                                             account=transcript.strip() or "(no account was given)")]
    for f in frames:
        contents.append(f"Frame {f.index} (t = {f.t_s:.0f} s):")
        contents.append(types.Part.from_bytes(data=f.jpeg, mime_type="image/jpeg"))
    client = make_client()  # keep the reference: the SDK closes its connection when it is collected
    response = client.models.generate_content(
        model=config.GEMINI_VQA_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_OnePassInspection),
    )
    return _OnePassInspection.model_validate_json(response.text)


def plan_from_mentions(raw: _OnePassInspection, transcript: str, catalogue: dict[str, dict]) -> CuePlan:
    """After a one-pass answer: which signs did the account really mention? Quotes must appear in the account."""
    seen_text = _norm(transcript)
    issues: list[str] = []
    mentioned: dict[str, str] = {}
    for f in raw.findings:
        if f.cue_id not in catalogue or f.cue_id in mentioned or not f.mentioned_in_account:
            continue
        quote = (f.account_quote or "").strip()
        if quote and _norm(quote) in seen_text:
            mentioned[f.cue_id] = quote
        else:
            issues.append(f"{f.cue_id!r} was said to be mentioned in the account without a quote that appears in it, so it was treated as not mentioned.")

    cues = [PlannedCue(cue_id=cid, label=c["label"], question=c["question"],
                       source="transcript" if cid in mentioned else "baseline",
                       why="Mentioned in the account." if cid in mentioned else "Standard check.",
                       transcript_quote=mentioned.get(cid))
            for cid, c in catalogue.items()]
    cues.sort(key=lambda c: c.source != "transcript")  # stable: mentioned signs first, catalogue order kept
    presentations = sorted({p for cid in mentioned for p in catalogue[cid]["presentations"] if p != "any"})
    return CuePlan(presentations=presentations, cues=cues, issues=issues)


def _inspect(frames: list[Frame], plan: CuePlan) -> _RawInspection:
    from google.genai import types

    needs = {cid: c["needs"] for cid, c in load_catalogue().items()}
    cues = "\n".join(f"- {c.cue_id}: {c.question} (needs: {needs.get(c.cue_id, 'visible')})" for c in plan.cues)
    contents: list = [PROMPT.format(cues=cues)]
    for f in frames:
        contents.append(f"Frame {f.index} (t = {f.t_s:.0f} s):")
        contents.append(types.Part.from_bytes(data=f.jpeg, mime_type="image/jpeg"))
    client = make_client()  # keep the reference: the SDK closes its connection when it is collected
    response = client.models.generate_content(
        model=config.GEMINI_VQA_MODEL,
        contents=contents,
        config=types.GenerateContentConfig(response_mime_type="application/json", response_schema=_RawInspection),
    )
    return _RawInspection.model_validate_json(response.text)


def build_report(plan: CuePlan, raw: _RawInspection, frames: list[Frame]) -> VisualCueReport:
    """Turn the model's answers into a report, enforcing the grounding rules above."""
    issues: list[str] = []
    valid = {f.index for f in frames}
    answers = {}
    for r in raw.findings:
        answers.setdefault(r.cue_id, r)

    findings: list[CueFinding] = []
    for cue in plan.cues:
        r = answers.get(cue.cue_id)
        if r is None:
            findings.append(CueFinding(cue_id=cue.cue_id, label=cue.label, finding="cannot_assess",
                                       reason="No answer was obtained for this cue."))
            continue
        evidence = sorted({i for i in r.evidence_frames if i in valid})[:MAX_EVIDENCE_FRAMES]
        if len(evidence) < len(set(r.evidence_frames)):
            issues.append(f"Dropped frame numbers for {cue.cue_id!r} that do not exist.")
        finding, reason, confidence = r.finding, r.reason.strip(), max(0.0, min(1.0, r.confidence))
        if finding == "present" and not evidence:
            issues.append(f"{cue.cue_id!r} was claimed present without frame evidence, so it was not accepted.")
            finding, confidence = "cannot_assess", 0.0
            reason = f"Not accepted: no frame evidence. Model said: {reason}"
        findings.append(CueFinding(cue_id=cue.cue_id, label=cue.label, finding=finding, confidence=confidence,
                                   reason=reason, evidence_frames=evidence))

    by_id = {f.cue_id: f for f in findings}
    not_seen = [c.label for c in plan.cues if c.source == "transcript" and by_id[c.cue_id].finding != "present"]
    return VisualCueReport(
        plan=plan,
        findings=findings,
        frames=[FrameInfo(index=f.index, t_s=f.t_s) for f in frames],
        reported_but_not_seen=not_seen,
        neurological_cues=to_neurological_cues(by_id),
        issues=issues,
    )


def to_neurological_cues(by_id: dict[str, CueFinding]) -> NeurologicalCues:
    """Map stroke-related findings onto the PRD's NeurologicalCues. Unassessed stays None."""

    def flag(cue_id: str) -> bool | None:
        f = by_id.get(cue_id)
        if f is None or f.finding == "cannot_assess":
            return None
        return f.finding == "present"

    face, gaze, arm = flag("face_droop"), flag("gaze_deviation"), flag("arm_weakness")
    # Only a positive is reported: the speech part of the Cincinnati scale is not assessed from video.
    positive = True if (face or arm) else None
    return NeurologicalCues(
        facial_asymmetry_detected=face, gaze_deviation_detected=gaze, gross_motor_deficit=arm,
        cincinnati_scale_positive=positive,
        notes=["Speech is not assessed from video, so a missing positive is not a negative."],
    )
