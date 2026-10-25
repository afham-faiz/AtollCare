import json
import subprocess

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.models.schemas import RppgEstimates
from src.services import cue_log, cue_planner, results_log, video_analysis, vqa_evaluator
from src.services.cue_planner import _Pick, _Picks, load_catalogue
from src.services.vqa_evaluator import _RawFinding, _RawInspection

ACCOUNT = "He is gasping for air and clutching his chest."
VITALS = RppgEstimates(heart_rate_bpm=88, respiration_rate_bpm=18, signal_quality_score=0.7, uncalibrated=False,
                       source="presage", heart_rate_quality=0.7, respiration_quality=0.7)


@pytest.fixture(scope="module")
def video() -> bytes:
    import os
    import tempfile
    out = os.path.join(tempfile.mkdtemp(), "t.mp4")
    subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-y", "-loglevel", "error", "-f", "lavfi", "-i",
                    "testsrc=duration=6:size=320x240:rate=10", "-pix_fmt", "yuv420p", out], check=True)
    return open(out, "rb").read()


@pytest.fixture
def gemini(monkeypatch):
    """A working (fake) Gemini: the inspector cites frame 2 for every cue it is asked about."""
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)
    monkeypatch.setattr(cue_planner, "_ask_planner", lambda *a: _Picks(
        presentations=["respiratory distress"],
        cues=[_Pick(cue_id="laboured_breathing", why="Gasping.", transcript_quote="gasping for air")]))
    seen = {}

    def inspect(frames, plan):
        seen["cue_ids"] = [c.cue_id for c in plan.cues]
        return _RawInspection(findings=[_RawFinding(cue_id=c.cue_id, finding="present", confidence=0.8,
                                                    reason="seen", evidence_frames=[2]) for c in plan.cues])

    monkeypatch.setattr(vqa_evaluator, "_inspect", inspect)
    return seen


def post(video, **data):
    return TestClient(app).post("/api/analyse-video", files={"video": ("clip.mp4", video, "video/mp4")}, data=data)


def test_with_an_account_only_the_relevant_signs_are_checked(monkeypatch, video, gemini):
    monkeypatch.setattr(video_analysis, "sidecar_mode", lambda: "sdk")
    monkeypatch.setattr(video_analysis, "extract_vitals_from_video", lambda v: VITALS)
    body = post(video, transcript=ACCOUNT, presage="true").json()
    assert body["used_account"] is True
    assert gemini["cue_ids"][0] == "laboured_breathing" and len(gemini["cue_ids"]) < len(load_catalogue())
    assert body["vitals"]["heart_rate_bpm"] == 88 and body["vitals_note"] is None
    assert list(body["signs"]["evidence"]) == ["2"]


def test_with_no_account_every_sign_is_checked(monkeypatch, video, gemini):
    monkeypatch.setattr(video_analysis, "sidecar_mode", lambda: "sdk")
    monkeypatch.setattr(video_analysis, "extract_vitals_from_video", lambda v: VITALS)
    body = post(video, transcript="", presage="true").json()
    assert body["used_account"] is False
    assert set(gemini["cue_ids"]) == set(load_catalogue())


def test_presage_can_be_switched_off(monkeypatch, video, gemini):
    monkeypatch.setattr(video_analysis, "extract_vitals_from_video", lambda v: pytest.fail("Presage must not run"))
    body = post(video, transcript=ACCOUNT, presage="false").json()
    assert body["vitals"] is None and "switched off" in body["vitals_note"]
    assert body["signs"]["report"]["findings"]


def test_a_stopped_presage_service_does_not_block_the_signs(monkeypatch, video, gemini):
    monkeypatch.setattr(video_analysis, "sidecar_mode", lambda: None)
    body = post(video, presage="true").json()
    assert body["vitals"] is None and "not running" in body["vitals_note"]
    assert body["signs"]["report"]["findings"]


def test_a_failing_gemini_does_not_block_presage(monkeypatch, video):
    monkeypatch.setattr(video_analysis, "sidecar_mode", lambda: "sdk")
    monkeypatch.setattr(video_analysis, "extract_vitals_from_video", lambda v: VITALS)
    body = post(video, transcript=ACCOUNT, presage="true").json()        # no API key -> Gemini unavailable
    assert body["vitals"]["heart_rate_bpm"] == 88
    assert body["signs"]["report"]["issues"][0].startswith("inspection_failed")


def test_each_part_is_logged_for_the_developer_panel(monkeypatch, video, gemini, tmp_path):
    monkeypatch.setattr(results_log, "LOG_PATH", tmp_path / "results.json")
    monkeypatch.setattr(video_analysis, "sidecar_mode", lambda: "sdk")
    monkeypatch.setattr(video_analysis, "extract_vitals_from_video", lambda v: VITALS)
    post(video, transcript=ACCOUNT, presage="true")
    assert json.load(open(results_log.LOG_PATH, encoding="utf-8"))[0]["result"]["heart_rate_bpm"] == 88
    assert json.load(open(cue_log.LOG_PATH, encoding="utf-8"))[0]["transcript"] == ACCOUNT


def test_empty_upload_is_rejected():
    assert TestClient(app).post("/api/analyse-video", files={"video": ("a.mp4", b"", "video/mp4")}).status_code == 400
