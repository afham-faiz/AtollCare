# Shared contract — Pydantic models are THE single source of truth. TS types are generated from these via OpenAPI
# (`bun run gen:api`). Add fields here; never invent alternative shapes in routers or the web app.
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.intake.schemas import Demographics, RppgEstimates, VisualCueReport


# ---------------------------------------------------------------- enums
class TransferStatus(str, Enum):
    preparing = "preparing"  # crew assessing; handoff not yet sent (not visible to the hospital)
    pending = "pending"  # handoff sent, awaiting hospital acceptance
    accepted = "accepted"  # en route, receiving team accepted and is preparing
    arrived = "arrived"  # handed over at the destination
    closed = "closed"


class TransportMode(str, Enum):
    road = "road"
    boat = "boat"
    helicopter = "helicopter"
    plane = "plane"


class VitalsSource(str, Enum):
    presage = "presage"  # contactless, Presage SmartSpectra via presage-bridge
    manual = "manual"  # entered by the crew
    simulated = "simulated"  # demo stand-in when no Presage bridge is connected


class MonitoringSource(str, Enum):
    presage = "presage"  # live camera stream through the bridge
    simulated = "simulated"
    scan = "scan"  # vitals come from 60 s scans (phone); nothing streams or is simulated between them
    off = "off"


class Consciousness(str, Enum):
    alert = "A"
    confused = "C"
    voice = "V"
    pain = "P"
    unresponsive = "U"


class NoteKind(str, Enum):
    voice = "voice"  # crew voice note (transcribed)
    text = "text"  # crew typed note
    question = "question"  # hospital → crew, spoken in the vehicle
    message = "message"  # hospital → crew information (e.g. acceptance)
    answer = "answer"  # crew reply to a question
    alert = "alert"  # deterioration alert raised by the engine
    event = "event"  # lifecycle (created, accepted, arrived, …)


class Author(str, Enum):
    crew = "crew"
    hospital = "hospital"
    system = "system"
    companion = "companion"  # the person with the patient, from the pre-arrival phone


class AlertLevel(str, Enum):
    warning = "warning"
    critical = "critical"


# ---------------------------------------------------------------- reference data
class GeoPoint(BaseModel):
    lat: float
    lng: float


class Facility(BaseModel):
    id: str
    name: str
    short_name: str
    kind: Literal["hospital", "clinic"]
    lat: float
    lng: float


class TransportModeInfo(BaseModel):
    mode: TransportMode
    label: str
    speed_kmh: float
    detour: float


class RegionSummary(BaseModel):
    id: str
    name: str
    country: str
    description: str


class Region(RegionSummary):
    emergency_number: str | None = None  # shown to a companion before anything else: call this first
    timezone: str
    center: GeoPoint
    zoom: int
    modes: list[TransportMode]
    facilities: list[Facility]


# ---------------------------------------------------------------- transfer parts
class Patient(BaseModel):
    label: str | None = None  # never a real name in the demo
    age: int | None = None
    sex: Literal["M", "F", "X"] | None = None


class VitalsReading(BaseModel):
    id: UUID
    transfer_id: UUID
    recorded_at: datetime
    source: VitalsSource
    heart_rate: float | None = None
    resp_rate: float | None = None
    hrv_rmssd: float | None = None
    spo2: float | None = None
    on_oxygen: bool | None = None
    systolic_bp: float | None = None
    temperature_c: float | None = None
    consciousness: Consciousness | None = None
    confidence: float | None = None
    low_quality: bool = False  # confidence < 0.6 → kept but excluded from NEWS2


class LatestValue(BaseModel):
    value: float | str | bool
    at: datetime
    source: VitalsSource
    flag: str | None = None  # e.g. "outside Presage's cleared range — confirm manually"


class News2Result(BaseModel):
    total: int | None
    components: dict[str, int | None]
    any_single_3: bool
    band: Literal["low", "low_medium", "medium", "high"] | None
    complete: bool
    missing: list[str]
    values_used: dict[str, Any] = {}


class Alert(BaseModel):
    code: str
    level: AlertLevel
    text: str
    since: datetime


class Extraction(BaseModel):
    observations: list[str] = []
    interventions: list[str] = []


class Note(BaseModel):
    id: UUID
    transfer_id: UUID
    at: datetime
    author: Author
    kind: NoteKind
    text: str
    reply_to: UUID | None = None
    extraction: Extraction | None = None
    extracted_by: Literal["gemini", "rules"] | None = None
    audio_url: str | None = None


class Intervention(BaseModel):
    at: datetime
    text: str
    note_id: UUID


class RemoveInterventionRequest(BaseModel):
    """The crew strike an item the extraction got wrong; their original words stay in the timeline."""

    note_id: UUID
    text: str


class Briefing(BaseModel):
    situation: str
    background: str
    assessment: str
    recommendation: str
    suspected_condition: str | None = None
    generated_by: Literal["gemini", "template"]
    generated_at: datetime
    input_hash: str = ""


class DeteriorationForecast(BaseModel):
    slope_per_hour: float
    projected_news2_at_arrival: float | None
    minutes_to_news2_7: float | None
    trend: Literal["improving", "stable", "worsening"]
    confidence: Literal["low", "medium"]
    points_used: int
    horizon_min: float | None = None
    r2: float | None = None
    hr_slope_per_hour: float | None = None
    rr_slope_per_hour: float | None = None


class SimProfile(BaseModel):
    heart_rate: float = 92
    heart_rate_per_hour: float = 8
    resp_rate: float = 18
    resp_rate_per_hour: float = 3
    hrv_rmssd: float = 28


class Monitoring(BaseModel):
    source: MonitoringSource = MonitoringSource.simulated
    last_reading_at: datetime | None = None
    hint: str | None = None  # latest Presage framing hint ("face too far")


class PresageCheck(BaseModel):
    """The crew's oximeter pulse against the nearest camera heart rate (within 10 min before it)."""

    at: datetime
    camera: int
    reference: int  # the oximeter's pulse, as the crew entered it
    agrees: bool  # within 5 bpm
    disputed: bool  # more than 10 bpm apart: the oximeter's value is the one used


class Acceptance(BaseModel):
    by: str
    at: datetime
    prepare: list[str] = []
    message: str | None = None


class Transfer(BaseModel):
    id: UUID
    code: str  # e.g. "AC-4F2K" — short, readable over a radio
    region_id: str
    created_at: datetime
    updated_at: datetime
    status: TransferStatus
    patient: Patient
    complaint: str
    origin_id: str
    destination_id: str
    mode: TransportMode
    departed_at: datetime
    eta: datetime
    distance_km: float
    progress: float = Field(0, ge=0, le=1)
    position: GeoPoint
    origin_point: GeoPoint
    destination_point: GeoPoint
    monitoring: Monitoring = Monitoring()
    sim_profile: SimProfile = SimProfile()
    latest: dict[str, LatestValue] = {}
    news2: News2Result | None = None
    alerts: list[Alert] = []
    alerts_announced: dict[str, datetime] = {}  # code → last time it was announced (spoken / timeline)
    briefing: Briefing | None = None
    handoff_at: datetime | None = None
    acceptance: Acceptance | None = None
    interventions: list[Intervention] = []
    notes: list[Note] = []
    vitals: list[VitalsReading] = []  # most recent 120, oldest first
    arrived_at: datetime | None = None
    pre_arrival: PreArrival | None = None  # the companion's packet this transfer started from, as it arrived
    scans: list[Scan] = []  # recorded clips during the transfer (phone): vitals + visible signs
    presage_checks: list[PresageCheck] = []  # camera heart rate against the crew's oximeter, every time it was entered


class TransferListItem(BaseModel):
    id: UUID
    code: str
    region_id: str
    status: TransferStatus
    patient: Patient
    complaint: str
    suspected_condition: str | None
    origin_id: str
    destination_id: str
    mode: TransportMode
    eta: datetime
    progress: float
    news2_total: int | None
    news2_band: str | None
    alert_level: AlertLevel | None
    heart_rate: float | None
    resp_rate: float | None
    monitoring: MonitoringSource
    unanswered_questions: int
    updated_at: datetime


# ---------------------------------------------------------------- pre-arrival (Part 1) and scans
class ScanStatus(str, Enum):
    processing = "processing"
    done = "done"
    failed = "failed"


class Scan(BaseModel):
    """One recorded clip (about 60 s, phone propped up): Presage heart and breathing rate and Gemini's check for
    visible signs, both from the same video. The video itself is not kept; only frames a finding cites are."""

    id: UUID
    at: datetime  # when it was recorded
    status: ScanStatus = ScanStatus.processing
    stage: str | None = None  # what is happening now, in words, for the screen
    vitals: RppgEstimates | None = None
    vitals_note: str | None = None  # why there are no vitals, if so
    signs: VisualCueReport | None = None
    evidence: dict[str, str] = {}  # frame number → image URL, only for frames a finding cites
    error: str | None = None
    seconds: dict[str, float] = {}
    recorded: bool = False  # its vitals are already in the transfer's readings (written exactly once)
    noted: bool = False  # its one-line summary is already on the transfer's timeline


class IntakeStatus(str, Enum):
    draft = "draft"  # the companion is still filling it in
    sent = "sent"  # sent to the health centre; waiting for someone to start a transfer
    started = "started"  # a transfer was started from it


class Intake(BaseModel):
    """The pre-arrival packet from the companion's phone: who the patient is, what happened in their own words,
    and what one recorded clip showed. Captured once, then carried into the transfer and never asked again."""

    id: UUID
    code: str  # e.g. "PA-7K2Q"
    region_id: str
    status: IntakeStatus = IntakeStatus.draft
    created_at: datetime
    updated_at: datetime
    health_centre_id: str | None = None  # where they are heading
    patient: Patient = Patient()
    account: str | None = None  # the companion's own words (transcribed or typed)
    account_source: Literal["voice", "text"] | None = None
    complaint: str | None = None  # one line, condensed from the account
    identity: Demographics | None = None  # read from an ID photo; needs_review unless every field was clear
    scans: list[Scan] = []
    sent_at: datetime | None = None
    transfer_id: UUID | None = None


class PreArrival(BaseModel):
    """The packet as the transfer received it (a copy, so later edits to the intake don't rewrite history)."""

    intake_id: UUID
    code: str
    sent_at: datetime | None = None
    account: str | None = None
    account_source: Literal["voice", "text"] | None = None
    identity: Demographics | None = None
    scans: list[Scan] = []


class CreateIntakeRequest(BaseModel):
    region_id: str | None = None  # default: the active region
    health_centre_id: str | None = None


class UpdateIntakeRequest(BaseModel):
    patient: Patient | None = None
    health_centre_id: str | None = None
    account: str | None = Field(None, max_length=4000)  # typed instead of spoken


class StartTransferRequest(BaseModel):
    origin_id: str | None = None  # default: the intake's health centre
    destination_id: str
    mode: TransportMode


# ---------------------------------------------------------------- requests
class CreateTransferRequest(BaseModel):
    patient: Patient = Patient()
    complaint: str = Field(min_length=1)
    origin_id: str
    destination_id: str
    mode: TransportMode


class VitalsRequest(BaseModel):
    source: VitalsSource = VitalsSource.manual
    recorded_at: datetime | None = None
    heart_rate: float | None = Field(None, ge=10, le=300)
    resp_rate: float | None = Field(None, ge=1, le=80)
    hrv_rmssd: float | None = Field(None, ge=0, le=500)
    spo2: float | None = Field(None, ge=40, le=100)
    on_oxygen: bool | None = None
    systolic_bp: float | None = Field(None, ge=30, le=300)
    temperature_c: float | None = Field(None, ge=25, le=45)
    consciousness: Consciousness | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    hint: str | None = None


class NoteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    kind: Literal["voice", "text", "answer"] = "text"
    reply_to: UUID | None = None


class HeardRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class HeardVitals(BaseModel):
    """Vitals read out of something said. Nothing is recorded until the crew saves them (or says them in a note)."""
    transcript: str
    spo2: float | None = None
    on_oxygen: bool | None = None
    systolic_bp: float | None = None
    diastolic_bp: float | None = None  # said with it, shown back; NEWS2 scores the systolic only
    temperature_c: float | None = None
    heart_rate: float | None = None
    resp_rate: float | None = None
    consciousness: Consciousness | None = None


class MessageRequest(BaseModel):
    text: str = Field(min_length=1, max_length=500)
    kind: Literal["question", "message"] = "question"
    sender: str | None = None


class AcceptRequest(BaseModel):
    by: str = Field(min_length=1, max_length=120)
    prepare: list[str] = []
    message: str | None = None


class MonitoringRequest(BaseModel):
    source: MonitoringSource


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    voice: Literal["crew", "hospital"] = "hospital"


class DemoStatePatch(BaseModel):
    speed_multiplier: float | None = Field(None, gt=0, le=600)
    region_id: str | None = None


class DemoCase(BaseModel):
    id: str
    region_id: str
    title: str
    patient: Patient
    complaint: str
    origin_id: str
    destination_id: str
    mode: TransportMode
    suggested_note: str | None = None
    # what the presenter types into "Complete NEWS2" — never pre-entered as if the crew had measured it
    suggested_vitals: str | None = None


class BridgeHeartbeat(BaseModel):
    sdk: Literal["ready", "no_api_key", "unavailable", "error"]
    version: str | None = None
    clients: int = 0
    message: str | None = None


# ---------------------------------------------------------------- state & responses
class DemoState(BaseModel):
    speed_multiplier: float = 1
    clock_offset_min: float = 0
    clock_anchor_real: datetime | None = None
    region_id: str = "maldives"


class AdapterStatus(BaseModel):
    presage: Literal["live", "simulated"]
    gemini: Literal["real", "mock"]
    elevenlabs: Literal["real", "mock"]
    storage: Literal["real", "mock"]


class BridgeStatus(BaseModel):
    connected: bool
    sdk: str | None = None
    version: str | None = None
    message: str | None = None
    last_seen: datetime | None = None


class InfraStatus(BaseModel):
    """Where this engine is running and what it stores data in — read from the environment, never assumed."""

    host: str  # "Vultr" (from the instance metadata service) or "Local"
    host_region: str | None = None  # e.g. "lhr"
    host_plan: str | None = None  # e.g. "vc2-2c-4gb"
    database: str  # "Tiger Cloud", "TimescaleDB", "PostgreSQL" or "In-memory"
    database_version: str | None = None


class MetaResponse(BaseModel):
    region: Region  # active region for new transfers
    regions: list[Region]  # every installed pack (existing transfers may belong to another)
    modes: list[TransportModeInfo]
    adapters: AdapterStatus
    bridge: BridgeStatus
    demo_state: DemoState
    now: datetime
    prepare_options: list[str]
    infra: InfraStatus


# ---------------------------------------------------------------- network insights (Tiger Data)
class InsightsKpis(BaseModel):
    transfers: int
    handed_off: int
    accepted: int
    median_min_to_accept: float | None
    p90_min_to_accept: float | None
    median_journey_min: float | None
    high_risk: int  # NEWS2 ≥ 7 at the latest score


class InsightsDay(BaseModel):
    day: datetime
    transfers: int = 0
    alerts: int = 0
    questions: int = 0
    readings: int = 0


class InsightsDestination(BaseModel):
    destination_id: str
    name: str
    transfers: int
    median_min_to_accept: float | None


class StorageTable(BaseModel):
    name: str
    rows: int
    chunks: int
    compressed_chunks: int
    bytes_before_compression: int | None
    bytes_after_compression: int | None
    total_bytes: int


class TimedQuery(BaseModel):
    name: str
    source: str  # the table or continuous aggregate that answered it
    ms: float


class InsightsResponse(BaseModel):
    available: bool
    reason: str | None = None
    database: str
    database_version: str | None = None
    days: int
    seeded_transfers: int = 0
    live_transfers: int = 0
    kpis: InsightsKpis | None = None
    daily: list[InsightsDay] = []
    destinations: list[InsightsDestination] = []
    storage: list[StorageTable] = []
    aggregates: list[str] = []
    queries: list[TimedQuery] = []


class BenchmarkResponse(BaseModel):
    question: str
    days: int
    aggregate_source: str
    aggregate_ms: float
    raw_ms: float
    rows_scanned: int
    speedup: float


class SeedHistoryResponse(BaseModel):
    transfers: int
    readings: int
    notes: int
    compressed_chunks: int
    seconds: float


class HealthResponse(BaseModel):
    ok: bool
    db: str
    adapters: AdapterStatus


class OkResponse(BaseModel):
    ok: bool = True


class VitalsAck(BaseModel):
    news2: News2Result | None
    alerts: list[Alert]
    monitoring: Monitoring


class TrendBucket(BaseModel):
    t: datetime
    hr: float | None = None
    rr: float | None = None
    hrv: float | None = None
    spo2: float | None = None
    sbp: float | None = None
    temp: float | None = None
    news2: int | None = None


class TrendResponse(BaseModel):
    buckets: list[TrendBucket]  # measured readings only (Presage, crew)
    source: Literal["vitals_1m", "raw", "memory"]
    query_ms: float | None = None  # how long the database took to answer
    forecast: DeteriorationForecast | None = None


class TranscribeResponse(BaseModel):
    text: str
    language: str
    source: Literal["elevenlabs", "unavailable"]


class SpeakResponse(BaseModel):
    audio_url: str | None
    source: Literal["elevenlabs", "browser"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


# forward references (Transfer → PreArrival, Scan) resolve once every class above exists
Transfer.model_rebuild()
