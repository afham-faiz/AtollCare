# Shared contract — Pydantic models are THE single source of truth. TS types are generated from these via OpenAPI
# (`bun run gen:api`). Add fields here; never invent alternative shapes in routers or the web app.
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
    presage = "presage"
    simulated = "simulated"
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
    flag: str | None = None  # e.g. "outside Presage validated range — confirm manually"


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
    """Where this engine is running and what it stores data in — detected, not assumed."""

    database: str  # "Tiger Cloud · TimescaleDB 2.17" | "TimescaleDB 2.17" | "PostgreSQL 16" | "In-memory (demo)"
    database_kind: Literal["tiger_cloud", "timescaledb", "postgres", "memory"]
    host: str  # "Vultr · LHR" | "This computer"
    host_provider: str | None = None  # "vultr" when detected from the instance metadata service
    host_region: str | None = None
    host_source: Literal["metadata", "env", "none"] = "none"


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


class HealthResponse(BaseModel):
    ok: bool
    db: str
    adapters: AdapterStatus
    infra: InfraStatus | None = None


# ---------------------------------------------------------------- network insights (Tiger Data)
class TransferLogRow(BaseModel):
    """One completed transfer in the `transfer_log` hypertable."""

    transfer_id: UUID
    departed_at: datetime
    region_id: str
    origin_id: str
    destination_id: str
    mode: TransportMode
    channel: Literal["atollcare", "radio"]
    condition: str | None = None
    handoff_at: datetime | None = None
    accepted_at: datetime | None = None
    arrived_at: datetime
    journey_min: float
    warning_min: float | None = None
    accept_min: float | None = None
    prepared: bool = False
    peak_news2: int | None = None
    seeded: bool = False


class InsightsTotals(BaseModel):
    transfers: int
    seeded: int
    warning_hours: float  # total hours receiving teams knew a patient was coming before arrival
    median_warning_min: float | None
    median_accept_min: float | None
    p90_accept_min: float | None
    median_journey_min: float | None
    prepared_pct: float | None


class InsightsDay(BaseModel):
    day: datetime
    transfers: int
    atollcare: int
    radio: int
    avg_warning_min: float | None
    avg_accept_min: float | None


class InsightsChannel(BaseModel):
    channel: Literal["atollcare", "radio"]
    transfers: int
    median_warning_min: float | None
    median_accept_min: float | None
    prepared_pct: float | None


class InsightsGroup(BaseModel):
    key: str  # mode, destination id or local hour
    transfers: int
    median_journey_min: float | None = None
    median_warning_min: float | None = None
    median_accept_min: float | None = None


class InsightsResponse(BaseModel):
    region_id: str
    days: int
    since: datetime
    source: Literal["transfer_daily", "raw", "memory"]  # daily series from the continuous aggregate when available
    query_ms: float
    totals: InsightsTotals
    daily: list[InsightsDay]
    channels: list[InsightsChannel]
    by_mode: list[InsightsGroup]
    by_destination: list[InsightsGroup]
    by_hour: list[InsightsGroup]  # local hour of departure, "00".."23"


class SeedResponse(BaseModel):
    inserted: int
    days: int
    region_id: str
    elapsed_ms: float


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
    buckets: list[TrendBucket]
    source: Literal["vitals_1m", "raw", "memory"]
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
