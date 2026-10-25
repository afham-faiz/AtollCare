import subprocess
from types import SimpleNamespace

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.services import vqa_evaluator
from src.services.cue_planner import load_catalogue
from src.services.video_prep import Frame
from src.services.vqa_evaluator import (_OnePassFinding, _OnePassInspection, evaluate_one_pass, plan_from_mentions,
                                        run_visual_cue_session)

ACCOUNT = "He is gasping for air, and clutching his chest. His lips look pale."


@pytest.fixture(scope="module")
def video() -> bytes:
    import os
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "t.mp4")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=6:size=320x240:rate=10", "-pix_fmt", "yuv420p", out], check=True)
    return open(out, "rb").read()


def finding(cue_id, finding="absent", mentioned=False, quote=None, frames=(), confidence=0.8, reason="r"):
    return _OnePassFinding(cue_id=cue_id, finding=finding, confidence=confidence, reason=reason,
                           evidence_frames=list(frames), mentioned_in_account=mentioned, account_quote=quote)


def answer_all(overrides: dict):
    """A full one-pass answer: every catalogue sign 'absent' unless overridden."""
    return _OnePassInspection(findings=[overrides.get(cid) or finding(cid) for cid in load_catalogue()])


# ---------------------------------------------------------------- reading the mentions

def test_mentioned_signs_come_first_with_verified_quotes():
    raw = answer_all({
        "laboured_breathing": finding("laboured_breathing", mentioned=True, quote="gasping for air"),
        "chest_clutching": finding("chest_clutching", mentioned=True, quote="CLUTCHING his chest"),   # case is irrelevant
    })
    plan = plan_from_mentions(raw, ACCOUNT, load_catalogue())
    assert len(plan.cues) == len(load_catalogue())                                  # every sign is checked
    assert [c.cue_id for c in plan.cues[:2]] == ["laboured_breathing", "chest_clutching"]
    assert [c.source for c in plan.cues[:2]] == ["transcript"] * 2
    assert all(c.source == "baseline" for c in plan.cues[2:])
    assert plan.cues[0].transcript_quote == "gasping for air"
    assert plan.presentations == ["cardiac", "respiratory distress"]               # derived from the catalogue, not the model


def test_a_mention_without_a_real_quote_is_not_accepted():
    raw = answer_all({
        "sweating": finding("sweating", mentioned=True, quote="drenched in sweat"),      # not in the account
        "pain_grimace": finding("pain_grimace", mentioned=True, quote=None),             # no quote at all
    })
    plan = plan_from_mentions(raw, ACCOUNT, load_catalogue())
    by_id = {c.cue_id: c for c in plan.cues}
    assert by_id["sweating"].source == "baseline" and by_id["pain_grimace"].source == "baseline"
    assert len(plan.issues) == 2


def test_no_account_means_nothing_is_mentioned():
    plan = plan_from_mentions(answer_all({}), "", load_catalogue())
    assert all(c.source == "baseline" for c in plan.cues) and plan.presentations == []


# ---------------------------------------------------------------- the full one-pass session

def test_one_pass_reports_each_sign_separately_and_enforces_grounding(monkeypatch, video):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vqa_evaluator, "_inspect_one_pass", lambda fs, t, a, c: answer_all({
        "laboured_breathing": finding("laboured_breathing", "present", True, "gasping for air", frames=[2, 99]),
        "chest_clutching": finding("chest_clutching", "absent", True, "clutching his chest"),
        "face_droop": finding("face_droop", "present", frames=[]),                      # no evidence -> rejected
    }))
    report, frames = evaluate_one_pass(video, ACCOUNT)
    by_id = {f.cue_id: f for f in report.findings}
    assert len(report.findings) == len(load_catalogue()) and len(frames) == 3
    assert by_id["laboured_breathing"].finding == "present" and by_id["laboured_breathing"].evidence_frames == [2]
    assert by_id["face_droop"].finding == "cannot_assess"                                # grounding rule still applies
    assert report.reported_but_not_seen == ["Hand pressed to the chest"]                  # mentioned, not seen
    assert report.diagnostics["mode"] == "one_pass"


def test_the_prompt_asks_all_signs_with_the_account_and_the_independence_rule(monkeypatch):
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen["contents"], seen["schema"] = contents, config.response_schema
            return SimpleNamespace(text=_OnePassInspection().model_dump_json())

    monkeypatch.setattr(vqa_evaluator, "make_client", lambda: SimpleNamespace(models=FakeModels()))
    frames = [Frame(index=1, t_s=0.0, jpeg=b"\xff\xd8\xff"), Frame(index=2, t_s=2.0, jpeg=b"\xff\xd8\xff")]
    vqa_evaluator._inspect_one_pass(frames, ACCOUNT, 54, load_catalogue())
    text = " ".join(c for c in seen["contents"] if isinstance(c, str))
    assert ACCOUNT in text and "Patient age: 54" in text and "Frame 2" in text
    assert all(f"- {cid}:" in text for cid in load_catalogue())                          # every sign is asked
    assert "must NOT influence Part B" in text
    assert seen["schema"] is _OnePassInspection                                          # forced per-sign JSON answers


def test_an_empty_account_is_stated_as_such(monkeypatch):
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen["text"] = " ".join(c for c in contents if isinstance(c, str))
            return SimpleNamespace(text=_OnePassInspection().model_dump_json())

    monkeypatch.setattr(vqa_evaluator, "make_client", lambda: SimpleNamespace(models=FakeModels()))
    vqa_evaluator._inspect_one_pass([Frame(index=1, t_s=0.0, jpeg=b"\xff\xd8\xff")], "  ", None, load_catalogue())
    assert "(no account was given)" in seen["text"] and "Patient age: unknown" in seen["text"]


def test_one_pass_never_raises(monkeypatch, video):
    report, frames = evaluate_one_pass(b"garbage", ACCOUNT)
    assert frames == [] and report.issues[0].startswith("inspection_failed") and len(report.findings) == len(load_catalogue())
    report, _ = evaluate_one_pass(video, ACCOUNT)                                        # no API key
    assert "GEMINI_API_KEY" in report.issues[0]
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(vqa_evaluator, "_inspect_one_pass", lambda *a: (_ for _ in ()).throw(RuntimeError("model down")))
    report, _ = evaluate_one_pass(video, ACCOUNT)
    assert "model down" in report.issues[0] and all(f.finding == "cannot_assess" for f in report.findings)


# ---------------------------------------------------------------- choosing the mode

def test_vqa_mode_chooses_one_request_or_two(monkeypatch):
    calls = []
    monkeypatch.setattr(vqa_evaluator, "evaluate_one_pass", lambda *a: calls.append("one_pass") or "ONE")
    monkeypatch.setattr(vqa_evaluator, "plan_cues", lambda *a: calls.append("plan") or "PLAN")
    monkeypatch.setattr(vqa_evaluator, "evaluate_visual_cues", lambda v, plan: calls.append("two_step") or "TWO")
    monkeypatch.setattr(config, "VQA_MODE", "one_pass")
    assert run_visual_cue_session(b"v", "t") == "ONE" and calls == ["one_pass"]
    calls.clear()
    monkeypatch.setattr(config, "VQA_MODE", "two_step")
    assert run_visual_cue_session(b"v", "t") == "TWO" and calls == ["plan", "two_step"]


def test_vqa_mode_must_be_one_of_the_two_values(monkeypatch):
    monkeypatch.setenv("VQA_MODE", "both")
    with pytest.raises(config.ConfigError, match="one_pass, two_step"):
        config._required_choice("VQA_MODE", ("one_pass", "two_step"))
    monkeypatch.setenv("VQA_MODE", "One_Pass")
    assert config._required_choice("VQA_MODE", ("one_pass", "two_step")) == "one_pass"


def test_the_endpoint_reports_a_missing_vqa_mode_clearly(monkeypatch, video):
    def boom(*a, **k):
        raise config.ConfigError("VQA_MODE is not set. Add a line VQA_MODE=... to inputs/.env")
    monkeypatch.setattr("src.app.analyse_video", boom)
    resp = TestClient(app).post("/api/analyse-video", files={"video": ("a.mp4", video, "video/mp4")})
    assert resp.status_code == 500 and "VQA_MODE" in resp.json()["detail"]
