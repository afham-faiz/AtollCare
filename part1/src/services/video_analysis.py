"""One video in, everything we can see out.

The video is shrunk once. Then, at the same time:
- Presage measures heart and breathing rate (optional: the user can switch it off), and
- Gemini checks the video for visible signs. If a voice account exists it decides which signs to
  look for; if not, every sign in the catalogue is checked.
A failure in one part never stops the other.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from src.models.schemas import RppgEstimates, VisualCueReport
from src.services.rppg_extractor import extract_vitals_from_video
from src.services.sidecar_manager import sidecar_mode
from src.services.video_prep import Frame, downsample_video
from src.services.vqa_evaluator import run_visual_cue_session


@dataclass
class VideoAnalysis:
    small: bytes                       # the shrunken copy that was analysed
    report: VisualCueReport
    frames: list[Frame]
    estimates: RppgEstimates | None    # None when Presage was switched off or unavailable
    vitals_note: str | None            # why there are no vitals, if so
    sizes_mb: dict
    seconds: dict


def _timed(fn, *args):
    started = time.time()
    result = fn(*args)
    return result, round(time.time() - started, 1)


def _measure_vitals(video: bytes) -> RppgEstimates | None:
    if sidecar_mode() is None:
        return None
    return extract_vitals_from_video(video)


def analyse_video(raw: bytes, transcript: str = "", age: int | None = None, use_presage: bool = True) -> VideoAnalysis:
    small, shrink_s = _timed(downsample_video, raw)
    with ThreadPoolExecutor(max_workers=2) as pool:
        cues_job = pool.submit(_timed, run_visual_cue_session, small, transcript, age)
        vitals_job = pool.submit(_timed, _measure_vitals, small) if use_presage else None
        (report, frames), cues_s = cues_job.result()
        estimates, vitals_s = vitals_job.result() if vitals_job else (None, 0.0)

    note = None
    if not use_presage:
        note = "Heart and breathing rate were switched off."
    elif estimates is None:
        note = "The Presage service is not running, so heart and breathing rate were not measured."
    return VideoAnalysis(
        small=small, report=report, frames=frames, estimates=estimates, vitals_note=note,
        sizes_mb={"original": round(len(raw) / 1e6, 1), "sent": round(len(small) / 1e6, 1)},
        seconds={"downsample": shrink_s, "signs": cues_s, "presage": vitals_s},
    )
