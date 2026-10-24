from typing import Literal

from pydantic import BaseModel, Field


class Demographics(BaseModel):
    """Identity read from an ID document. Unreadable fields are None, never guessed."""

    full_name: str | None = None
    id_number: str | None = None
    age: int | None = None
    # A driving licence says nothing about insurance, so this stays UNKNOWN unless another source verifies it.
    insurance_status: Literal["VERIFIED", "UNKNOWN", "NONE"] = "UNKNOWN"
    # Not part of the hand-off contract: helpful for the health-centre clerk.
    date_of_birth: str | None = None  # ISO date, e.g. 1990-01-01
    document_type: str | None = None
    needs_review: bool = True         # True unless every field was clearly read
    issues: list[str] = []
    diagnostics: dict = {}


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
