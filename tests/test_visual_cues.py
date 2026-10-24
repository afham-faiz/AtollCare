import json
import subprocess
from types import SimpleNamespace

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.models.schemas import CuePlan, PlannedCue
from src.services import cue_log, cue_planner, vqa_evaluator
from src.services.cue_planner import _Pick, _Picks, build_plan, load_catalogue, plan_cues
from src.services.video_prep import Frame, sample_frames
from src.services.vqa_evaluator import _RawFinding, _RawInspection, build_report, evaluate_visual_cues

ACCOUNT = "He is gasping for air and bending double, clutching his chest, and his lips look pale."


@pytest.fixture(scope="module")
def video() -> bytes:
    """A 6 s synthetic video (10 fps), so frame sampling can be tested without real footage."""
    import os
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "t.mp4")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=6:size=320x240:rate=10", "-pix_fmt", "yuv420p", out], check=True)
    return open(out, "rb").read()


def cue(cid, source="transcript"):
    c = load_catalogue()[cid]
    return PlannedCue(cue_id=cid, label=c["label"], question=c["question"], source=source)


def frames(n=3):
    return [Frame(index=i, t_s=float(i * 2), jpeg=b"\xff\xd8\xff" + bytes(10)) for i in range(1, n + 1)]


# ---------------------------------------------------------------- catalogue

def test_catalogue_is_complete_and_has_baseline_cues():
    catalogue = load_catalogue()
    assert len(catalogue) >= 10
    for cid, c in catalogue.items():
        assert c["id"] == cid and c["label"] and "?" in c["question"] and c["needs"] and c["presentations"]
    assert {"face_droop", "responsiveness", "pallor_or_blue_lips"} <= {c["id"] for c in catalogue.values() if c["baseline"]}


# ---------------------------------------------------------------- planner

def test_plan_keeps_valid_picks_and_adds_baseline_cues():
    picks = _Picks(presentations=["respiratory distress", "cardiac"], cues=[
        _Pick(cue_id="laboured_breathing", why="Gasping.", transcript_quote="gasping for air"),
        _Pick(cue_id="chest_clutching", why="Clutching.", transcript_quote="clutching his chest"),
    ])
    plan = build_plan(picks, ACCOUNT, load_catalogue())
    ids = [c.cue_id for c in plan.cues]
    assert ids[:2] == ["laboured_breathing", "chest_clutching"]
    assert {"face_droop", "responsiveness", "pallor_or_blue_lips"} <= set(ids)
    assert [c.source for c in plan.cues[:2]] == ["transcript", "transcript"]
    assert all(c.source == "baseline" for c in plan.cues[2:])
    assert plan.presentations == ["respiratory distress", "cardiac"] and plan.issues == []


def test_plan_ignores_invented_cues_and_duplicates():
    picks = _Picks(cues=[_Pick(cue_id="heart_attack_detector"), _Pick(cue_id="sweating"), _Pick(cue_id="sweating")])
    plan = build_plan(picks, ACCOUNT, load_catalogue())
    ids = [c.cue_id for c in plan.cues]
    assert "heart_attack_detector" not in ids and ids.count("sweating") == 1
    assert any("heart_attack_detector" in i for i in plan.issues)


def test_a_quote_that_is_not_in_the_account_is_removed():
    picks = _Picks(cues=[_Pick(cue_id="pallor_or_blue_lips", transcript_quote="his skin has turned purple"),
                         _Pick(cue_id="laboured_breathing", transcript_quote="Gasping for AIR")])
    plan = build_plan(picks, ACCOUNT, load_catalogue())
    by_id = {c.cue_id: c for c in plan.cues}
    assert by_id["pallor_or_blue_lips"].transcript_quote is None
    assert by_id["laboured_breathing"].transcript_quote == "Gasping for AIR"   # case does not matter
    assert any("not found in the account" in i for i in plan.issues)


def test_unknown_presentations_are_dropped():
    plan = build_plan(_Picks(presentations=["cardiac", "alien abduction", "any"]), ACCOUNT, load_catalogue())
    assert plan.presentations == ["cardiac"]


def test_plan_is_capped():
    ids = [c for c in load_catalogue()][:11]
    plan = build_plan(_Picks(cues=[_Pick(cue_id=i) for i in ids]), ACCOUNT, load_catalogue())
    assert len([c for c in plan.cues if c.source == "transcript"]) == cue_planner.MAX_PICKS


def test_empty_account_checks_every_sign():
    plan = plan_cues("   ")
    assert {c.cue_id for c in plan.cues} == set(load_catalogue())
    assert all(c.source == "baseline" for c in plan.cues) and plan.issues


def test_no_key_checks_every_sign_with_a_reason():
    plan = plan_cues(ACCOUNT)
    assert {c.cue_id for c in plan.cues} == set(load_catalogue()) and "GEMINI_API_KEY" in plan.issues[0]


def test_planner_failure_never_raises(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(cue_planner, "_ask_planner", lambda *a: (_ for _ in ()).throw(RuntimeError("503")))
    plan = plan_cues(ACCOUNT)
    assert {c.cue_id for c in plan.cues} == set(load_catalogue()) and "503" in plan.issues[0]


def test_plan_uses_the_model_picks(monkeypatch):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(cue_planner, "_ask_planner",
                        lambda *a: _Picks(cues=[_Pick(cue_id="chest_clutching", transcript_quote="clutching his chest")]))
    plan = plan_cues(ACCOUNT, age=54)
    assert plan.cues[0].cue_id == "chest_clutching" and plan.cues[0].source == "transcript"


# ---------------------------------------------------------------- grounding rules

def report_for(findings, plan_ids=("face_droop", "laboured_breathing"), n_frames=3):
    plan = CuePlan(cues=[cue(i, "transcript" if i == "laboured_breathing" else "baseline") for i in plan_ids])
    return build_report(plan, _RawInspection(findings=findings), frames(n_frames))


def test_present_needs_evidence_frames():
    r = report_for([_RawFinding(cue_id="laboured_breathing", finding="present", confidence=0.9, reason="mouth open",
                                evidence_frames=[2]),
                    _RawFinding(cue_id="face_droop", finding="present", confidence=0.8, reason="looks drooped")])
    by_id = {f.cue_id: f for f in r.findings}
    assert by_id["laboured_breathing"].finding == "present" and by_id["laboured_breathing"].evidence_frames == [2]
    assert by_id["face_droop"].finding == "cannot_assess" and by_id["face_droop"].confidence == 0.0
    assert "Not accepted" in by_id["face_droop"].reason
    assert any("face_droop" in i for i in r.issues)


def test_nonexistent_frame_numbers_are_dropped():
    r = report_for([_RawFinding(cue_id="laboured_breathing", finding="present", evidence_frames=[2, 99])])
    f = next(f for f in r.findings if f.cue_id == "laboured_breathing")
    assert f.evidence_frames == [2]


def test_a_present_claim_citing_only_fake_frames_is_rejected():
    r = report_for([_RawFinding(cue_id="laboured_breathing", finding="present", evidence_frames=[42])])
    f = next(f for f in r.findings if f.cue_id == "laboured_breathing")
    assert f.finding == "cannot_assess"


def test_unanswered_cues_become_cannot_assess():
    r = report_for([])
    assert [f.finding for f in r.findings] == ["cannot_assess", "cannot_assess"]


def test_confidence_is_clamped():
    r = report_for([_RawFinding(cue_id="face_droop", finding="absent", confidence=7.0)])
    assert next(f for f in r.findings if f.cue_id == "face_droop").confidence == 1.0


def test_reported_but_not_seen_lists_account_cues_the_video_did_not_show():
    r = report_for([_RawFinding(cue_id="laboured_breathing", finding="absent", confidence=0.8, reason="calm"),
                    _RawFinding(cue_id="face_droop", finding="absent", confidence=0.9)])
    assert r.reported_but_not_seen == ["Visible effort to breathe"]   # face_droop was baseline, not claimed
    r2 = report_for([_RawFinding(cue_id="laboured_breathing", finding="present", evidence_frames=[1])])
    assert r2.reported_but_not_seen == []


def test_stroke_cues_map_onto_neurological_cues():
    ids = ("face_droop", "gaze_deviation", "arm_weakness")
    r = report_for([_RawFinding(cue_id="face_droop", finding="present", evidence_frames=[1]),
                    _RawFinding(cue_id="gaze_deviation", finding="absent"),
                    _RawFinding(cue_id="arm_weakness", finding="cannot_assess")], plan_ids=ids)
    n = r.neurological_cues
    assert n.facial_asymmetry_detected is True and n.gaze_deviation_detected is False
    assert n.gross_motor_deficit is None            # not assessed is not the same as not seen
    assert n.cincinnati_scale_positive is True


def test_no_stroke_signs_never_claims_a_negative_cincinnati():
    r = report_for([_RawFinding(cue_id="face_droop", finding="absent")], plan_ids=("face_droop",))
    assert r.neurological_cues.facial_asymmetry_detected is False
    assert r.neurological_cues.cincinnati_scale_positive is None   # speech is not assessed from video


# ---------------------------------------------------------------- frame sampling

def test_frames_are_evenly_spaced_and_numbered_from_one(video):
    fs = sample_frames(video, every_s=2, max_frames=24, max_side=160)
    assert [f.index for f in fs] == [1, 2, 3] and [f.t_s for f in fs] == [0.0, 2.0, 4.0]
    assert all(f.jpeg[:3] == b"\xff\xd8\xff" for f in fs)


def test_frame_count_is_capped_by_widening_the_interval(video):
    fs = sample_frames(video, every_s=0.5, max_frames=3, max_side=160)
    assert len(fs) == 3 and fs[1].t_s == 2.0


def test_unreadable_video_raises_value_error():
    with pytest.raises(ValueError):
        sample_frames(b"not a video", every_s=2, max_frames=5)


# ---------------------------------------------------------------- inspector

def test_the_inspector_never_receives_the_account(monkeypatch):
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen["contents"] = contents
            return SimpleNamespace(text=_RawInspection().model_dump_json())

    monkeypatch.setattr(vqa_evaluator, "make_client", lambda: SimpleNamespace(models=FakeModels()))
    plan = CuePlan(cues=[PlannedCue(cue_id="laboured_breathing", label="x", question="Is breathing visibly hard?",
                                    source="transcript", why="He is gasping", transcript_quote="gasping for air")])
    vqa_evaluator._inspect(frames(2), plan)
    text = " ".join(c for c in seen["contents"] if isinstance(c, str))
    assert "Is breathing visibly hard?" in text and "Frame 2" in text
    assert "gasping" not in text and "He is" not in text      # neither the quote nor the reason leaks


def test_a_full_inspection_uses_real_frames_and_the_models_answers(monkeypatch, video):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vqa_evaluator, "_inspect", lambda fs, plan: _RawInspection(findings=[
        _RawFinding(cue_id=c.cue_id, finding="present", confidence=0.7, reason="seen", evidence_frames=[2])
        for c in plan.cues]))
    plan = CuePlan(cues=[cue("laboured_breathing")])
    report, fs = evaluate_visual_cues(video, plan)
    assert len(fs) == 3 and report.findings[0].evidence_frames == [2]
    assert [f.index for f in report.frames] == [1, 2, 3] and report.diagnostics["frames_sent"] == 3


def test_inspection_failures_never_raise(monkeypatch, video):
    plan = CuePlan(cues=[cue("laboured_breathing")])
    report, fs = evaluate_visual_cues(b"garbage", plan)                 # unreadable video
    assert fs == [] and report.findings[0].finding == "cannot_assess" and "inspection_failed" in report.issues[0]
    report, _ = evaluate_visual_cues(video, plan)                       # no API key
    assert "GEMINI_API_KEY" in report.issues[0]
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vqa_evaluator, "_inspect", lambda *a: (_ for _ in ()).throw(RuntimeError("model down")))
    report, _ = evaluate_visual_cues(video, plan)
    assert "model down" in report.issues[0] and report.findings[0].finding == "cannot_assess"


# ---------------------------------------------------------------- endpoint

def test_endpoint_runs_the_session_returns_evidence_and_logs(monkeypatch, video):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)
    monkeypatch.setattr(cue_planner, "_ask_planner", lambda *a: _Picks(
        presentations=["respiratory distress"],
        cues=[_Pick(cue_id="laboured_breathing", why="Gasping.", transcript_quote="gasping for air")]))
    monkeypatch.setattr(vqa_evaluator, "_inspect", lambda fs, plan: _RawInspection(findings=[
        _RawFinding(cue_id="laboured_breathing", finding="present", confidence=0.8, reason="open mouth", evidence_frames=[2])]))

    resp = TestClient(app).post("/api/visual-cues", files={"video": ("clip.mp4", video, "video/mp4")},
                                data={"transcript": ACCOUNT, "age": "54"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["report"]["plan"]["cues"][0]["cue_id"] == "laboured_breathing"
    assert list(body["evidence"]) == ["2"] and body["evidence"]["2"]["data_url"].startswith("data:image/jpeg;base64,")
    logged = json.load(open(cue_log.LOG_PATH, encoding="utf-8"))
    assert logged[0]["video"] == "clip.mp4" and logged[0]["transcript"] == ACCOUNT
    assert logged[0]["evidence_files"]["2"].startswith("/recordings/cue-frame_")


def test_endpoint_rejects_an_empty_upload():
    assert TestClient(app).post("/api/visual-cues", files={"video": ("a.mp4", b"", "video/mp4")}).status_code == 400


def test_endpoint_survives_an_unreadable_video():
    resp = TestClient(app).post("/api/visual-cues", files={"video": ("a.mp4", b"junk", "video/mp4")},
                                data={"transcript": ACCOUNT})
    assert resp.status_code == 200 and resp.json()["report"]["issues"][0].startswith("inspection_failed")
