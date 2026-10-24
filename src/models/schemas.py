from typing import Literal

from pydantic import BaseModel, Field


class RppgEstimates(BaseModel):
    heart_rate_bpm: int | None = None
    respiration_rate_bpm: int | None = None
    # Per-vital confidence (0-1). Overall score below is the lower of the two reported vitals.
    heart_rate_quality: float | None = None
    respiration_quality: float | None = None
    signal_quality_score: float = Field(0.0, ge=0.0, le=1.0)
    # True when quality is too low to trust the numbers (score < 0.4).
    uncalibrated: bool = True
    source: Literal["presage", "mock", "unavailable"] = "unavailable"
    # Presage readiness problems, e.g. kTooDark, kExcessiveMotion.
    issues: list[str] = []
    # Not part of the hand-off contract: per-sample traces and camera-check counts for inspection/logging.
    diagnostics: dict = {}
