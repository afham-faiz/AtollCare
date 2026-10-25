import os
import subprocess
import tempfile

import imageio_ffmpeg
import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app
from src.models.schemas import RppgEstimates
from src.services import cue_planner, video_analysis, video_prep, vqa_evaluator
from src.services.cue_planner import _Picks
from src.services.video_prep import downsample_video, sample_frames
from src.services.vqa_evaluator import _RawFinding, _RawInspection

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()


@pytest.fixture(scope="module")
def browser_webm() -> bytes:
    """6 s of VP8 streamed to a pipe, so the file has no duration header: like a MediaRecorder recording."""
    proc = subprocess.run([FFMPEG, "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=duration=6:size=320x240:rate=15",
                           "-c:v", "libvpx", "-f", "webm", "pipe:1"], capture_output=True, check=True)
    return proc.stdout


def duration_of(data: bytes, suffix: str) -> float | None:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "x" + suffix)
        open(path, "wb").write(data)
        return video_prep._duration_s(path)


def test_the_test_recording_really_has_no_duration(browser_webm):
    assert duration_of(browser_webm, ".webm") is None        # that is what makes browser recordings awkward


def test_downsampling_turns_a_browser_webm_into_a_normal_mp4_with_a_duration(browser_webm):
    small = downsample_video(browser_webm)
    assert small != browser_webm and small[4:8] == b"ftyp"   # re-encoded to mp4, not passed through untouched
    assert 5.5 <= duration_of(small, ".mp4") <= 6.5


def test_frames_can_be_sampled_straight_from_a_webm_with_no_duration(browser_webm):
    frames = sample_frames(browser_webm, every_s=2, max_frames=24, max_side=160)
    assert [f.t_s for f in frames] == [0.0, 2.0, 4.0]


def test_the_page_receives_the_recording_length_from_the_settings():
    body = TestClient(app).get("/api/health").json()
    assert body["video_record"] == {"max_s": 60.0, "error": None}


def test_a_missing_recording_length_is_reported_not_fatal(monkeypatch):
    monkeypatch.delattr(config, "VIDEO_RECORD_MAX_S")
    monkeypatch.delenv("VIDEO_RECORD_MAX_S", raising=False)
    resp = TestClient(app).get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["video_record"]["max_s"] is None and "VIDEO_RECORD_MAX_S" in resp.json()["video_record"]["error"]


def test_a_camera_recording_goes_through_the_whole_analysis_and_is_kept(monkeypatch, browser_webm):
    monkeypatch.setattr(config, "GEMINI_API_KEY", "k")
    monkeypatch.setattr(config, "SAVE_RECORDINGS", True)
    monkeypatch.setattr(config, "VQA_MODE", "two_step")
    monkeypatch.setattr(cue_planner, "_ask_planner", lambda *a: _Picks())
    monkeypatch.setattr(vqa_evaluator, "_inspect", lambda fs, plan: _RawInspection(findings=[
        _RawFinding(cue_id=c.cue_id, finding="present", confidence=0.7, reason="seen", evidence_frames=[2]) for c in plan.cues]))
    monkeypatch.setattr(video_analysis, "sidecar_mode", lambda: "sdk")
    monkeypatch.setattr(video_analysis, "extract_vitals_from_video",
                        lambda v: RppgEstimates(heart_rate_bpm=77, signal_quality_score=0.6, uncalibrated=False, source="presage"))

    resp = TestClient(app).post("/api/analyse-video", files={"video": ("camera-2026-10-24.webm", browser_webm, "video/webm")},
                                data={"transcript": "", "presage": "true"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["vitals"]["heart_rate_bpm"] == 77
    assert list(body["signs"]["evidence"]) == ["2"]
    assert body["video_file"].startswith("/recordings/video_") and body["video_file"].endswith(".mp4")   # the analysed copy is kept
