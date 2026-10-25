import os
import statistics

import httpx

from src.models.schemas import RppgEstimates

QUALITY_THRESHOLD = 0.4
MIN_STABLE_SAMPLES = 3
SIDECAR_URL = os.environ.get("PRESAGE_SIDECAR_URL", "http://127.0.0.1:3001")
TIMEOUT_S = float(os.environ.get("PRESAGE_TIMEOUT_S", "300"))


def summarise_series(series: list[dict]) -> tuple[int | None, float]:
    """Collapse a Presage sample trace into (value, quality).

    Uses the median of stable samples (or of any sample with confidence > 0 when too few
    are stable) so a bad final second, e.g. the person moving as recording stops, cannot
    override a good minute. Quality is the mean confidence of those samples.
    """
    stable = [s for s in series if s.get("stable")]
    pool = stable if len(stable) >= MIN_STABLE_SAMPLES else [s for s in series if (s.get("confidence") or 0) > 0]
    if not pool:
        return None, 0.0
    value = round(statistics.median(s["value"] for s in pool))
    quality = statistics.mean(s.get("confidence") or 0.0 for s in pool)
    return value, max(0.0, min(1.0, quality))


def extract_vitals_from_video(video_bytes: bytes) -> RppgEstimates:
    """Send video to the Presage sidecar; never raises, degrades to null vitals."""
    try:
        resp = httpx.post(
            f"{SIDECAR_URL}/vitals",
            content=video_bytes,
            headers={"content-type": "application/octet-stream"},
            timeout=TIMEOUT_S,
        )
        resp.raise_for_status()
        data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        return RppgEstimates(issues=[f"sidecar_unavailable: {exc.__class__.__name__}"])

    diagnostics = data.get("diagnostics") or {}
    hr, hr_q = _vital(diagnostics.get("pulse_series"), data.get("heart_rate_bpm"), data.get("confidence"))
    rr, rr_q = _vital(diagnostics.get("breathing_series"), data.get("respiration_rate_bpm"), data.get("confidence"))

    qualities = [q for v, q in ((hr, hr_q), (rr, rr_q)) if v is not None]
    # Conservative overall score: the weakest vital we are reporting.
    quality = min(qualities) if qualities else 0.0
    return RppgEstimates(
        heart_rate_bpm=hr,
        respiration_rate_bpm=rr,
        heart_rate_quality=hr_q if hr is not None else None,
        respiration_quality=rr_q if rr is not None else None,
        signal_quality_score=quality,
        uncalibrated=quality < QUALITY_THRESHOLD,
        source="mock" if data.get("mode") == "mock" else "presage",
        issues=data.get("issues") or [],
        diagnostics=diagnostics,
    )


def _vital(series: list[dict] | None, fallback_value, fallback_confidence) -> tuple[int | None, float]:
    """Prefer the whole-trace summary; fall back to the sidecar's single value (mock mode)."""
    if series:
        return summarise_series(series)
    if fallback_value is None:
        return None, 0.0
    return fallback_value, max(0.0, min(1.0, float(fallback_confidence or 0.0)))
