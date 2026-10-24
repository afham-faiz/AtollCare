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


class NeurologicalCues(BaseModel):
    """PRD contract. None means 'not assessed', which is different from False ('looked, not seen')."""

    facial_asymmetry_detected: bool | None = None
    gaze_deviation_detected: bool | None = None
    gross_motor_deficit: bool | None = None
    # Face and arm only: the speech part of the Cincinnati scale is not assessed from video.
    cincinnati_scale_positive: bool | None = None
    notes: list[str] = []


class PlannedCue(BaseModel):
    cue_id: str
    label: str
    question: str
    source: Literal["transcript", "baseline"]
    why: str = ""
    # Words from the bystander's account that prompted this cue (checked to really appear in it).
    transcript_quote: str | None = None


class CuePlan(BaseModel):
    presentations: list[str] = []
    cues: list[PlannedCue] = []
    issues: list[str] = []


class CueFinding(BaseModel):
    cue_id: str
    label: str
    finding: Literal["present", "absent", "cannot_assess"]
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    reason: str = ""
    # Frame numbers (see VisualCueReport.frames) that show the finding. 'present' always has at least one.
    evidence_frames: list[int] = []


class FrameInfo(BaseModel):
    index: int
    t_s: float


class VisualCueReport(BaseModel):
    plan: CuePlan
    findings: list[CueFinding] = []
    frames: list[FrameInfo] = []
    # Cues the account suggested that the video did not show (absent or could not be assessed).
    reported_but_not_seen: list[str] = []
    neurological_cues: NeurologicalCues = NeurologicalCues()
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
