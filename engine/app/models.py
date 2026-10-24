# Shared contract — Pydantic models are THE single source of truth (§6). TS types are generated from these
# via OpenAPI (`bun run gen:api`). Add fields here, never invent alternative shapes in routers or the web app.
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# ---------------------------------------------------------------- enums (§6.1)
class CaseStatus(str, Enum):
    draft = "draft"
    submitted = "submitted"
    assessed = "assessed"
    referred = "referred"
    needs_info = "needs_info"
    accepted = "accepted"
    declined = "declined"
    dispatched = "dispatched"
    in_transit = "in_transit"
    arrived = "arrived"
    closed = "closed"


class Severity(str, Enum):
    low = "low"
    low_medium = "low_medium"
    medium = "medium"
    high = "high"
    critical = "critical"


SEVERITY_ORDER = ["low", "low_medium", "medium", "high", "critical"]


class TransportMode(str, Enum):
    ground = "ground"
    speedboat = "speedboat"
    sea_ambulance = "sea_ambulance"
    seaplane = "seaplane"
    fixed_wing = "fixed_wing"
    helicopter = "helicopter"


class Consciousness(str, Enum):
    alert = "A"
    confused = "C"
    voice = "V"
    pain = "P"
    unresponsive = "U"


class VitalsSource(str, Enum):
    presage = "presage"
    manual = "manual"
    device = "device"
    mock = "mock"


class EventType(str, Enum):
    created = "created"
    submitted = "submitted"
    vitals_added = "vitals_added"
    intake_extracted = "intake_extracted"
    assessed = "assessed"
    referred = "referred"
    needs_info = "needs_info"
    info_provided = "info_provided"
    accepted = "accepted"
    declined = "declined"
    replanned = "replanned"
    dispatched = "dispatched"
    departed = "departed"
    leg_completed = "leg_completed"
    arrived = "arrived"
    closed = "closed"
    note = "note"


ActorRole = Literal["reporter", "clinician", "specialist", "transport", "system", "demo"]


# ---------------------------------------------------------------- reference data
class GeoPoint(BaseModel):
    lat: float
    lng: float


class Facility(BaseModel):
    id: str
    name: str
    short_name: str = ""
    type: Literal["tertiary_hospital", "regional_hospital", "atoll_hospital", "health_centre", "airport"]
    atoll: str
    lat: float
    lng: float
    capabilities: list[str] = []
    has_airport: bool = False
    nearest_airport_id: str | None = None
    lagoon_access: bool = False
    seaplane_base_id: str | None = None  # seaplanes land here instead (e.g. IGMH → Hulhulé), then ground leg

    @property
    def point(self) -> GeoPoint:
        return GeoPoint(lat=self.lat, lng=self.lng)

    @property
    def label(self) -> str:
        return self.short_name or self.name


class TransportModeInfo(BaseModel):
    mode: TransportMode
    label: str
    speed_kmh: float
    dispatch_min: float
    handover_min: float
    medic_onboard: bool = False
    enabled: bool = True
    constraints: str = ""


class ConditionInfo(BaseModel):
    id: str
    label: str
    window_min: float | None
    window_from: str
    window_label: str = ""
    time_critical: bool = False
    required_capabilities: list[str] = []
    high_severity_capabilities: list[str] = []
    interim_label: str | None = None


class TransportAsset(BaseModel):
    id: str
    mode: TransportMode
    home_facility_id: str
    status: Literal["available", "busy", "offline"]
    crew_note: str | None = None


class HospitalCapacity(BaseModel):
    facility_id: str
    icu_beds_free: int | None = None
    cath_lab_available: bool | None = None
    ct_available: bool | None = None
    blood_bank_units: int | None = None
    updated_at: datetime


class Weather(BaseModel):
    sea_state: int = Field(2, ge=0, le=9)
    wind_kt: float = 10
    visibility_km: float = 10


class DemoState(BaseModel):
    clock_offset_min: float = 0
    speed_multiplier: float = 1
    weather: Weather = Weather()
    night_override: bool | None = None
    # Extra fields (contract additions): real-time anchor for the speed multiplier, helicopter toggle, autoplay
    clock_anchor_real: datetime | None = None
    helicopter_enabled: bool = False


# ---------------------------------------------------------------- case parts (§6.2)
class Patient(BaseModel):
    name: str | None = None
    age: int | None = None
    sex: Literal["M", "F", "X"] | None = None
    pregnant: bool | None = None
    known_conditions: list[str] = []
    medications: list[str] = []
    allergies: list[str] = []


class VitalsReading(BaseModel):
    id: UUID
    case_id: UUID
    recorded_at: datetime
    source: VitalsSource
    heart_rate: float | None = None
    resp_rate: float | None = None
    spo2: float | None = None
    on_oxygen: bool | None = None
    systolic_bp: float | None = None
    temperature_c: float | None = None
    consciousness: Consciousness | None = None
    confidence: float | None = None
    media_url: str | None = None
    low_quality: bool = False  # F-M6.4: confidence < 0.6 → stored but excluded from NEWS2


class SuspectedCondition(BaseModel):
    condition_id: str
    probability: float = Field(ge=0, le=1)
    rationale: str = ""


class Intake(BaseModel):
    raw_text: str
    language: str = "en"
    chief_complaint: str
    symptoms: list[str] = []
    red_flags: list[str] = []
    onset_time: datetime | None = None
    onset_confidence: Literal["exact", "approx", "unknown"] = "unknown"
    suspected_conditions: list[SuspectedCondition] = []
    missing_info: list[str] = []
    extracted_by: Literal["gemini", "fallback_rules"]


class News2Result(BaseModel):
    total: int | None
    components: dict[str, int | None]
    any_single_3: bool
    band: Literal["low", "low_medium", "medium", "high"] | None
    complete: bool
    missing: list[str]
    values_used: dict[str, Any] = {}


class RouteLeg(BaseModel):
    mode: TransportMode
    from_id: str
    to_id: str
    from_point: GeoPoint
    to_point: GeoPoint
    distance_km: float
    dispatch_min: float
    travel_min: float
    handover_min: float
    depart_at: datetime
    arrive_at: datetime
    asset_id: str | None = None
    wait_min: float = 0  # time waiting for the asset to be ready (parallel dispatch)


class RouteOption(BaseModel):
    id: str
    destination_id: str
    legs: list[RouteLeg]
    total_min: float
    arrive_at: datetime
    feasible: bool
    infeasible_reasons: list[str] = []
    within_window: bool | None = None
    window_margin_min: float | None = None
    interim_stop_id: str | None = None
    score: float = 0
    # contract additions
    kind: Literal["direct", "interim", "local"] = "direct"
    label: str = ""
    medic_onboard: bool = False
    interim_arrive_min: float | None = None
    interim_within_window: bool | None = None
    score_breakdown: dict[str, float] = {}


class DeteriorationForecast(BaseModel):
    slope_per_hour: float
    projected_news2_at_arrival: float | None
    minutes_to_news2_7: float | None
    trend: Literal["improving", "stable", "worsening"]
    confidence: Literal["low", "medium"]
    points_used: int
    horizon_min: float | None = None  # how far ahead the projection actually extrapolates (≤ 2× observed span)
    r2: float | None = None
    hr_slope_per_hour: float | None = None
    rr_slope_per_hour: float | None = None


class BaselineStep(BaseModel):
    id: str
    label: str
    min: float


class BaselineComparison(BaseModel):
    steps: list[BaselineStep]
    baseline_total_min: float
    ours_steps: list[BaselineStep]
    ours_total_min: float
    saved_vs_baseline_min: float
    coordination_measured: bool
    assumptions: dict[str, Any] = {}


class Recommendation(BaseModel):
    severity: Severity
    primary_condition_id: str | None
    window_min: float | None
    time_since_onset_min: float | None
    destination_id: str
    required_capabilities: list[str]
    chosen_route_id: str
    alternatives: list[RouteOption]
    actions_now: list[str]
    explanation: str
    breach_warning: str | None = None
    forecast: DeteriorationForecast | None = None
    baseline: BaselineComparison
    generated_at: datetime
    engine_version: str
    # contract additions
    warnings: list[str] = []
    explanation_source: Literal["gemini", "template"] = "template"
    input_hash: str = ""
    onset_confidence: Literal["exact", "approx", "unknown"] = "unknown"
    window_from: Literal["onset", "first_medical_contact"] = "onset"
    interim_window_min: float | None = None
    condition_probabilities: list[SuspectedCondition] = []
    all_routes_count: int = 0


class SbarSummary(BaseModel):
    situation: str
    background: str
    assessment: str
    recommendation: str
    generated_by: Literal["gemini", "template"]
    input_hash: str = ""


class InfoAnswer(BaseModel):
    question: str
    answer: str
    at: datetime


class Referral(BaseModel):
    destination_id: str
    sent_at: datetime | None = None
    sbar: SbarSummary | None = None
    response: Literal["pending", "accepted", "declined", "needs_info"] = "pending"
    responded_at: datetime | None = None
    responder_name: str | None = None
    response_note: str | None = None
    info_requests: list[str] = []
    # contract additions
    note: str | None = None
    route_id: str | None = None
    info_answers: list[InfoAnswer] = []
    declined_destination_ids: list[str] = []


class TransportState(BaseModel):
    route_id: str | None = None
    status: Literal["none", "dispatched", "in_transit", "arrived"] = "none"
    current_leg_index: int | None = None
    position: GeoPoint | None = None
    eta: datetime | None = None
    asset_ids: list[str] = []
    # contract additions: frozen route schedule (rebased at dispatch) so the simulator survives restarts
    route: RouteOption | None = None
    dispatched_at: datetime | None = None
    legs_completed: int = 0


class CaseEvent(BaseModel):
    id: UUID
    case_id: UUID
    at: datetime
    type: EventType
    actor_role: str
    summary: str
    data: dict[str, Any] = {}


class CaseHeadline(BaseModel):
    elapsed_min: float
    projected_total_min: float | None
    saved_vs_baseline_min: float | None
    text: str


class CaseMeta(BaseModel):
    submitted_at: datetime | None = None
    referred_at: datetime | None = None
    accepted_at: datetime | None = None
    dispatched_at: datetime | None = None
    arrived_at: datetime | None = None
    closed_at: datetime | None = None
    outcome_note: str | None = None
    scenario_id: str | None = None
    scenario_started_at: datetime | None = None
    scenario_steps_done: int = 0
    autoplay: bool = False
    language: str = "en"
    last_assessed_at: datetime | None = None


class Case(BaseModel):
    id: UUID
    short_code: str
    created_at: datetime
    updated_at: datetime
    status: CaseStatus
    origin_facility_id: str
    origin_point: GeoPoint
    patient: Patient
    intake: Intake | None = None
    vitals: list[VitalsReading] = []
    news2: News2Result | None = None
    recommendation: Recommendation | None = None
    referral: Referral | None = None
    transport: TransportState = TransportState()
    timeline: list[CaseEvent] = []
    headline: CaseHeadline
    meta: CaseMeta = CaseMeta()


class CaseListItem(BaseModel):
    id: UUID
    short_code: str
    status: CaseStatus
    severity: Severity | None
    origin_facility_id: str
    destination_id: str | None
    primary_condition_id: str | None
    window_min: float | None
    window_remaining_min: float | None
    time_since_onset_min: float | None
    eta: datetime | None
    headline: CaseHeadline
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------- request bodies
class CreateCaseRequest(BaseModel):
    origin_facility_id: str
    patient: Patient | None = None
    raw_text: str | None = None


class PatchCaseRequest(BaseModel):
    patient: Patient | None = None
    origin_facility_id: str | None = None


class IntakeRequest(BaseModel):
    raw_text: str
    language: str | None = None


class ManualVitalsRequest(BaseModel):
    recorded_at: datetime | None = None
    source: VitalsSource = VitalsSource.manual
    heart_rate: float | None = None
    resp_rate: float | None = None
    spo2: float | None = None
    on_oxygen: bool | None = None
    systolic_bp: float | None = None
    temperature_c: float | None = None
    consciousness: Consciousness | None = None
    confidence: float | None = None
    media_url: str | None = None


class ReferRequest(BaseModel):
    destination_id: str | None = None
    route_id: str | None = None
    note: str | None = None


class RespondRequest(BaseModel):
    response: Literal["accepted", "declined", "needs_info"]
    responder_name: str
    note: str | None = None
    info_requests: list[str] = []


class InfoAnswersRequest(BaseModel):
    answers: dict[str, str]


class DispatchRequest(BaseModel):
    route_id: str
    asset_ids: list[str] | None = None


class CloseRequest(BaseModel):
    outcome_note: str = ""


class NoteRequest(BaseModel):
    text: str
    actor_role: str = "clinician"


class SpeakRequest(BaseModel):
    text: str
    voice: Literal["guide", "status"] = "guide"
    language: str | None = None


class CapacityPatch(BaseModel):
    icu_beds_free: int | None = None
    cath_lab_available: bool | None = None
    ct_available: bool | None = None
    blood_bank_units: int | None = None


class AssetPatch(BaseModel):
    status: Literal["available", "busy", "offline"]


class WeatherPatch(BaseModel):
    sea_state: int | None = Field(None, ge=0, le=9)
    wind_kt: float | None = None
    visibility_km: float | None = None


class DemoStatePatch(BaseModel):
    set_time_of_day: str | None = None  # "HH:MM" local (sim clock jumps to today at this time)
    clock_offset_min: float | None = None
    speed_multiplier: float | None = Field(None, gt=0, le=3600)
    weather: WeatherPatch | None = None
    night_override: bool | None = None
    clear_night_override: bool = False
    helicopter_enabled: bool | None = None


# ---------------------------------------------------------------- responses
class AdapterStatus(BaseModel):
    presage: str
    gemini: str
    elevenlabs: str
    storage: str


class ClockInfo(BaseModel):
    now: datetime
    local_time: str
    is_daylight: bool
    sunrise: str
    sunset: str
    seaplane_last_landing: str
    disabled_modes: dict[str, str]


class MetaResponse(BaseModel):
    facilities: list[Facility]
    transport_modes: list[TransportModeInfo]
    conditions: list[ConditionInfo]
    adapters: AdapterStatus
    demo_state: DemoState
    now: datetime
    clock: ClockInfo
    languages: list[dict[str, Any]]
    scenarios: list[dict[str, Any]]


class HealthResponse(BaseModel):
    ok: bool
    db: str
    adapters: AdapterStatus


class OkResponse(BaseModel):
    ok: bool = True


class ScanJobCreated(BaseModel):
    job_id: str


class ScanJobStatus(BaseModel):
    status: Literal["queued", "processing", "done", "failed"]
    reading: VitalsReading | None = None
    error: str | None = None
    case_id: UUID | None = None


class TrendBucket(BaseModel):
    t: datetime
    hr: float | None = None
    rr: float | None = None
    spo2: float | None = None
    sbp: float | None = None
    temp: float | None = None
    news2: int | None = None


class TrendResponse(BaseModel):
    buckets: list[TrendBucket]
    source: Literal["vitals_1m", "raw", "memory"]
    forecast: DeteriorationForecast | None = None


class TrackPoint(BaseModel):
    t: datetime
    lat: float
    lng: float
    leg_index: int | None = None


class TrackResponse(BaseModel):
    positions: list[TrackPoint]
    transport: TransportState


class TranscribeResponse(BaseModel):
    text: str
    language: str
    confidence: float | None = None
    source: Literal["elevenlabs", "mock"] = "mock"


class SpeakResponse(BaseModel):
    audio_url: str | None
    source: Literal["elevenlabs", "browser"] = "browser"


class GuidanceStep(BaseModel):
    id: str
    text: str
    audio_url: str | None = None


class GuidanceResponse(BaseModel):
    steps: list[GuidanceStep]
    source_condition_id: str
    disclaimer: str
    role: Literal["reporter", "clinician"]
    selected_by: Literal["gemini", "default_order"]


class CrewBriefResponse(BaseModel):
    text: str
    audio_url: str | None


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody
