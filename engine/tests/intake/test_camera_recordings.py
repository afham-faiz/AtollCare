import os
import subprocess
import tempfile

import imageio_ffmpeg
import pytest

from app.intake import video_prep
from app.intake.video_prep import downsample_video, sample_frames

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
        with open(path, "wb") as f:
            f.write(data)
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


