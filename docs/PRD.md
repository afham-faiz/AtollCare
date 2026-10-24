# PRD — **AtollLink**: Island-to-Specialist Emergency Coordination

> OxHack '26 · Team of 3 · 24h build · Version 1.0 (one-shot spec)
> Working name "AtollLink" — rename freely; it appears only in `web/src/app/config.ts` and the README.

---

## 0. Instructions for the building agent (read first)

You are building the **entire product in one pass**. Follow these rules:

1. **Build every feature in this document.** Priorities (`P0`/`P1`/`P2`) tell you the *order* to build in and what to protect if something breaks — they are **not** permission to skip. P2 features must exist at least in working, minimal form.
2. **Every external service sits behind an adapter with a `mock` mode.** The app must run end-to-end with **zero API keys** (`*_MODE=mock`) and switch to real services by setting env vars. Never let a missing key crash a page.
3. **Use the IDs.** Every module is `M#`, every feature is `F-M#.#`. Put the feature ID in a comment at the top of the file(s) that implement it (`// F-M3.2 Referral accept/decline`). Commit messages reference IDs (`feat(F-M2.4): routing engine`). This is how the team will find and fix things afterwards.
4. **Contracts are frozen.** The data model (§5) and API (§6) are the contract between three people who will each take over a lane after you finish. Do not invent alternative shapes. If you need a new field, add it to the Pydantic model (single source of truth) and regenerate TS types.
5. **Seed data and clinical numbers are illustrative.** Keep them in data files (`engine/app/data/*.json`, `*.yaml`), never hard-coded in logic, and label them `DEMO ASSUMPTION` in the UI where shown.
6. **Finish with:** `README.md` (run instructions), `docs/FEATURES.md` (checklist of every F-ID with ✅/⚠️ and file paths), `docs/KNOWN_ISSUES.md`, and `docs/DEV_POST.md` (draft). See §14.
7. Work in this order: §16 Build Order.

---

## 1. Problem

In archipelago nations like the **Maldives** (~190 inhabited islands spread over ~90,000 km² of ocean), the gap between "patient falls ill on an outer island" and "patient receives specialist treatment" is dominated not by medicine but by **coordination**:

- Island **health centres** have limited diagnostics; specialist care (cath lab, neurosurgery, ICU) is concentrated in **Malé (IGMH)**, with a handful of regional/atoll hospitals in between.
- Referral is a **sequential phone chain**: health centre → atoll/regional hospital → specialist in Malé → evacuation approval/funding → transport operator. Each hop waits for the previous one.
- **Transport is constrained**: speedboats and sea ambulances are slow over long distances; seaplanes are fast but **daylight-only** and weather-dependent; fixed-wing flights only connect islands with airports.
- Information is lost at each handoff (verbal history, no vitals trend, no timeline).

The result: time-critical conditions (heart attack, stroke, trauma, obstetric haemorrhage, sepsis) blow through their treatment windows.

**This is a problem of distance and handoffs, not money** — and it generalises to Pacific islands, Indonesia, the Philippines, the Scottish isles, and remote Arctic communities.

## 2. Solution (one sentence)

A shared, live **Case** that travels with the patient: contactless vitals and AI-structured intake at the island, a clinically-grounded **decision engine** that picks the fastest route to the *right* hospital within the condition's treatment window, one-click specialist acceptance in Malé, and live transport tracking — all handoffs happening **in parallel instead of in sequence**.

### Headline metric (shown on every screen that has a case)
> **"Symptom → definitive care: X h Y min. Estimated Z min faster than the phone-chain baseline."**

---

## 3. Users & Roles

No real auth. A **role switcher** in the header (stored in `localStorage`) selects the current role; every page is reachable by URL.

| Role | Where | Goal |
|---|---|---|
| **Reporter** (family member / community health worker) | `/report` — phone, mobile-first | Raise an alert fast, capture vitals, get first-aid guidance |
| **Island clinician** (health-centre doctor/nurse) | `/report/[caseId]` + `/hospital` (island view) | Add vitals/exam, confirm and send referral |
| **Specialist / coordinator** (Malé or regional hospital) | `/hospital` | Review incoming referrals, accept/decline/request info, see capacity |
| **Transport coordinator** | `/transport` | See recommended route, dispatch assets, track |
| **Demo operator** (us, on stage) | `/demo` | Reset, load scenarios, change clock/weather, accelerate time |

---

## 4. Hackathon tracks & how we use them

We target **6 prizes**. Solana and Snowflake are deliberately skipped (forced fits weaken the pitch).

| Track | Sponsor tech | What we build with it | Feature IDs | Judge-visible proof |
|---|---|---|---|---|
| **Best Use of Presage** | SmartSpectra SDK (contactless heart rate + breathing rate from a camera; FDA 510(k) cleared for iOS/Android; SDK also on Mac/Linux/Windows) | 30-second camera scan of the patient's face on the `/report` page → HR & RR feed NEWS2 severity score and the vitals trend | F-M6.* | Live scan of a teammate on stage; numbers flow into triage instantly |
| **Best Use of Gemini API** | Gemini (structured output via `google-genai`) | (1) messy free-text/voice intake → structured clinical JSON; (2) SBAR referral summary for the specialist; (3) plain-language explanation of the route decision; (4) selection from a *vetted* first-aid library | F-M2.2, F-M2.7, F-M2.8, F-M5.3 | "Our AI extracts, a clinical standard scores, an auditable optimiser decides" |
| **Best Use of ElevenLabs** | TTS + Speech-to-Text (Scribe) | (1) voice-note intake transcribed by Scribe; (2) spoken step-by-step first-aid guidance; (3) spoken status updates ("Sea ambulance arriving in 12 minutes") for family and crew | F-M5.* | Press "Speak", talk, watch intake fill; guidance read aloud |
| **Best Use of Tiger Data** | Tiger Cloud (TimescaleDB on Postgres) | Hypertables for `vitals_readings`, `transport_positions`, `case_events`; continuous aggregate for 1-min vitals buckets; `time_bucket` queries for trend charts and the deterioration forecast | F-M7.2, F-M2.6 | Vitals trend chart + live boat track served from hypertables |
| **Best Use of Vultr** | Vultr Cloud Compute + Vultr Object Storage | Whole stack deployed on a Vultr VM via Docker Compose + Caddy (HTTPS); scan videos & generated audio stored in Vultr Object Storage (S3-compatible) | F-M7.3, F-M7.4 | Public HTTPS URL judges can open on their phones |
| **DEV Writing Challenge** | dev.to post | Project story drafted in `docs/DEV_POST.md`, published by the team | F-M9.3 | Published link |

> ⚠️ **Presage integration risk.** Public info confirms native SDKs (iOS/Android/Mac/Linux/Windows); a browser/JS SDK is **not confirmed**. Therefore the vitals pipeline is: **browser records a 30 s video → uploads to engine → `PresageAdapter` processes it** (via the SDK on the Linux server, or Presage's cloud API if the booth provides one). Adapter modes: `sdk | cloud | mock | manual`. The team must confirm the real integration path with Presage at the start of the hackathon; the agent builds the adapter interface, the mock, and a best-effort real implementation clearly marked `TODO(presage-verify)`.

---

## 5. Architecture

```
┌──────────────────────────── Vultr VM (Docker Compose) ─────────────────────────────┐
│                                                                                     │
│  Caddy (HTTPS, reverse proxy)                                                       │
│    ├── /            → web    (Next.js, bun)   :3000                                 │
│    └── /api/*       → engine (FastAPI, uv)    :8000                                 │
│                                                                                     │
│  engine                                                                              │
│    ├── adapters/ presage · gemini · elevenlabs · storage   (each: real | mock)      │
│    ├── core/ news2 · conditions · routing · decision · baseline · forecast          │
│    ├── sim/ transport simulator (background task, accelerated clock)                │
│    └── db  ──────────────► Tiger Cloud (TimescaleDB)  [local: timescale container] │
│                                                                                     │
│  Object storage ─────────► Vultr Object Storage (S3)   [local: ./var/storage]      │
└─────────────────────────────────────────────────────────────────────────────────────┘

External: Gemini API · ElevenLabs API · Presage (SDK or cloud)
Frontend realtime = SWR polling every 2 s (no websockets).
```

**Key decisions**
- **The engine owns the database and all business logic.** Next.js is a pure frontend calling `/api/*`. Front-end never talks to the DB or third-party APIs directly (keys stay server-side).
- **Single source of truth for types:** Pydantic models in `engine/app/models.py` → OpenAPI → `openapi-typescript` generates `web/src/lib/api-types.ts` (`bun run gen:api`).
- **Simulated clock.** All engine logic uses `clock.now()` from `engine/app/core/clock.py`, which supports a demo offset and a speed multiplier. Needed so the night-time scenario works during a daytime pitch.

### 5.1 Repo layout

```
/
├── README.md
├── docker-compose.yml              # local dev: timescale + engine + web
├── docker-compose.prod.yml         # Vultr: + caddy
├── Caddyfile
├── .env.example
├── docs/
│   ├── PRD.md                      # this file
│   ├── FEATURES.md                 # F-ID checklist (agent-generated)
│   ├── KNOWN_ISSUES.md
│   ├── FEEDBACK.md                 # team's post-one-shot work log (template §15)
│   ├── PITCH.md                    # demo script + talking points
│   └── DEV_POST.md
├── engine/
│   ├── pyproject.toml              # uv
│   ├── Dockerfile
│   ├── app/
│   │   ├── main.py                 # FastAPI app, routers, CORS, startup (migrations, seed, sim)
│   │   ├── config.py               # pydantic-settings, all env vars
│   │   ├── models.py               # Pydantic models = THE contract (§6)
│   │   ├── db.py                   # async SQLAlchemy/asyncpg session
│   │   ├── migrations/001_init.sql # tables + hypertables + continuous aggregate (§6.3)
│   │   ├── routers/                # cases.py, assess.py, vitals.py, voice.py, transport.py, hospitals.py, demo.py, meta.py
│   │   ├── core/
│   │   │   ├── clock.py
│   │   │   ├── news2.py            # F-M2.3
│   │   │   ├── conditions.py       # F-M2.4
│   │   │   ├── routing.py          # F-M2.5
│   │   │   ├── decision.py         # F-M2.5
│   │   │   ├── forecast.py         # F-M2.6
│   │   │   ├── baseline.py         # F-M2.9
│   │   │   └── fallback_intake.py  # keyword rules when Gemini is unavailable
│   │   ├── adapters/
│   │   │   ├── presage.py          # F-M6.*
│   │   │   ├── gemini.py           # F-M2.2/2.7/2.8
│   │   │   ├── elevenlabs.py       # F-M5.*
│   │   │   └── storage.py          # S3 (Vultr) | local
│   │   ├── sim/transport_sim.py    # F-M4.4
│   │   └── data/
│   │       ├── facilities.json     # islands, hospitals, airports (§11)
│   │       ├── conditions.yaml     # time windows & capabilities (§8.3)
│   │       ├── transport_modes.yaml
│   │       ├── baseline.yaml       # phone-chain step durations
│   │       ├── first_aid.yaml      # vetted guidance library (§8.8)
│   │       └── scenarios/*.json    # demo scenarios (§12)
│   └── tests/                      # pytest (§13)
└── web/
    ├── package.json                # bun
    ├── src/
    │   ├── app/
    │   │   ├── layout.tsx
    │   │   ├── config.ts
    │   │   ├── (main)/
    │   │   │   ├── layout.tsx      # Header (role switcher) + Footer
    │   │   │   ├── page.tsx        # landing / overview
    │   │   │   ├── report/page.tsx, report/[caseId]/page.tsx
    │   │   │   ├── hospital/page.tsx, hospital/[caseId]/page.tsx
    │   │   │   ├── transport/page.tsx, transport/[caseId]/page.tsx
    │   │   │   ├── case/[caseId]/page.tsx   # read-only shared case view (family link)
    │   │   │   └── demo/page.tsx
    │   │   └── components/
    │   │       ├── (buttons)/ ButtonBase.tsx, ButtonPrimary.tsx, ButtonDanger.tsx
    │   │       ├── (pills)/ PillBase.tsx, PillSeverity.tsx, PillStatus.tsx
    │   │       ├── (modals)/ ModalBase.tsx, ModalPrimary.tsx
    │   │       ├── (case)/ CaseTimeline.tsx, CaseHeadline.tsx, VitalsChart.tsx, News2Card.tsx, RouteCard.tsx, SbarSummary.tsx
    │   │       ├── (map)/ AtollMap.tsx      # react-leaflet
    │   │       ├── (voice)/ VoiceRecorder.tsx, AudioPlayer.tsx
    │   │       ├── (vitals)/ CameraScan.tsx, ManualVitalsForm.tsx
    │   │       ├── Header.tsx
    │   │       └── Footer.tsx
    │   ├── lib/ api.ts (fetch wrapper), api-types.ts (generated), swr.ts, role.ts, format.ts
    │   └── styles/globals.css
    └── Dockerfile
```

### 5.2 Ownership lanes (for after the one-shot)

| Lane | Owner | Modules | Owns these directories |
|---|---|---|---|
| **A — Decision engine & AI** | AI/ML teammate | M2, M5 (backend), M6 (adapter) | `engine/app/core`, `engine/app/adapters`, `engine/app/data` |
| **B — Island / reporter experience** | Teammate 2 | M1, M6 (frontend), M5 (frontend) | `web/src/app/(main)/report`, `components/(vitals)`, `components/(voice)` |
| **C — Hospital & transport** | Teammate 3 | M3, M4, M8 | `web/src/app/(main)/hospital`, `/transport`, `/demo`, `components/(map)`, `engine/app/sim` |
| **Shared** | Whoever is free | M7, M9, `models.py`, `components/(case)` | Change only with a heads-up in the team chat |

---

## 6. Data model & contract

### 6.1 Enums

```python
class CaseStatus(str, Enum):
    draft = "draft"                 # reporter started, not submitted
    submitted = "submitted"         # alert raised from island
    assessed = "assessed"           # engine produced triage + recommendation
    referred = "referred"           # island clinician sent referral to destination hospital
    needs_info = "needs_info"       # specialist requested more info
    accepted = "accepted"           # destination hospital accepted
    declined = "declined"           # declined → engine re-plans to next-best destination
    dispatched = "dispatched"       # transport asset assigned
    in_transit = "in_transit"
    arrived = "arrived"             # at destination facility
    closed = "closed"               # handed over / outcome recorded

class Severity(str, Enum):  # derived from NEWS2 + red flags
    low = "low"; low_medium = "low_medium"; medium = "medium"; high = "high"; critical = "critical"

class TransportMode(str, Enum):
    ground = "ground"               # ambulance/walk on same island, or Hulhulé ↔ Malé bridge
    speedboat = "speedboat"
    sea_ambulance = "sea_ambulance"
    seaplane = "seaplane"           # daylight + weather constrained, lands at any lagoon
    fixed_wing = "fixed_wing"       # airport ↔ airport, night allowed
    helicopter = "helicopter"       # disabled in default data (toggle in /demo)

class Consciousness(str, Enum):  # ACVPU
    alert="A"; confused="C"; voice="V"; pain="P"; unresponsive="U"

class VitalsSource(str, Enum):
    presage="presage"; manual="manual"; device="device"; mock="mock"

class EventType(str, Enum):
    created="created"; submitted="submitted"; vitals_added="vitals_added"; intake_extracted="intake_extracted"
    assessed="assessed"; referred="referred"; needs_info="needs_info"; info_provided="info_provided"
    accepted="accepted"; declined="declined"; replanned="replanned"; dispatched="dispatched"
    departed="departed"; leg_completed="leg_completed"; arrived="arrived"; closed="closed"; note="note"
```

### 6.2 Core models (Pydantic, abbreviated — implement fully)

```python
class GeoPoint(BaseModel): lat: float; lng: float

class Patient(BaseModel):
    name: str | None; age: int | None; sex: Literal["M","F","X"] | None
    pregnant: bool | None; known_conditions: list[str] = []; medications: list[str] = []; allergies: list[str] = []

class VitalsReading(BaseModel):
    id: UUID; case_id: UUID; recorded_at: datetime; source: VitalsSource
    heart_rate: float | None; resp_rate: float | None; spo2: float | None
    on_oxygen: bool | None; systolic_bp: float | None; temperature_c: float | None
    consciousness: Consciousness | None
    confidence: float | None       # Presage/quality confidence 0–1
    media_url: str | None          # scan video in object storage

class Intake(BaseModel):            # Gemini structured output (F-M2.2)
    raw_text: str; language: str
    chief_complaint: str
    symptoms: list[str]; red_flags: list[str]
    onset_time: datetime | None; onset_confidence: Literal["exact","approx","unknown"]
    suspected_conditions: list[SuspectedCondition]   # {condition_id, probability 0–1, rationale}
    missing_info: list[str]         # questions the clinician should ask
    extracted_by: Literal["gemini","fallback_rules"]

class News2Result(BaseModel):
    total: int | None; components: dict[str, int | None]; any_single_3: bool
    band: Literal["low","low_medium","medium","high"] | None
    complete: bool; missing: list[str]

class RouteLeg(BaseModel):
    mode: TransportMode; from_id: str; to_id: str
    from_point: GeoPoint; to_point: GeoPoint
    distance_km: float; dispatch_min: float; travel_min: float; handover_min: float
    depart_at: datetime; arrive_at: datetime
    asset_id: str | None

class RouteOption(BaseModel):
    id: str; destination_id: str; legs: list[RouteLeg]
    total_min: float; arrive_at: datetime
    feasible: bool; infeasible_reasons: list[str]     # "seaplane: night", "weather: sea state 5"
    within_window: bool | None; window_margin_min: float | None
    interim_stop_id: str | None      # e.g. stabilise at regional hospital en route
    score: float

class Recommendation(BaseModel):
    severity: Severity
    primary_condition_id: str | None
    window_min: float | None; time_since_onset_min: float | None
    destination_id: str; required_capabilities: list[str]
    chosen_route_id: str; alternatives: list[RouteOption]   # top 3 incl. chosen, sorted by score
    actions_now: list[str]           # e.g. "Give aspirin 300 mg if no allergy (per protocol)", from vetted library only
    explanation: str                 # Gemini plain-language explanation (F-M2.8), fallback template
    breach_warning: str | None       # if no route meets window
    forecast: DeteriorationForecast | None
    baseline: BaselineComparison
    generated_at: datetime; engine_version: str

class SbarSummary(BaseModel):        # F-M2.7
    situation: str; background: str; assessment: str; recommendation: str
    generated_by: Literal["gemini","template"]

class Referral(BaseModel):
    destination_id: str; sent_at: datetime | None; sbar: SbarSummary | None
    response: Literal["pending","accepted","declined","needs_info"] = "pending"
    responded_at: datetime | None; responder_name: str | None
    response_note: str | None; info_requests: list[str] = []

class TransportState(BaseModel):
    route_id: str | None; status: Literal["none","dispatched","in_transit","arrived"]
    current_leg_index: int | None; position: GeoPoint | None; eta: datetime | None
    asset_ids: list[str] = []

class CaseEvent(BaseModel):
    id: UUID; case_id: UUID; at: datetime; type: EventType; actor_role: str; summary: str; data: dict = {}

class Case(BaseModel):
    id: UUID; short_code: str        # e.g. "AL-4F2K" for phone readout
    created_at: datetime; updated_at: datetime; status: CaseStatus
    origin_facility_id: str; origin_point: GeoPoint
    patient: Patient
    intake: Intake | None
    vitals: list[VitalsReading]      # latest 50, newest last
    news2: News2Result | None
    recommendation: Recommendation | None
    referral: Referral | None
    transport: TransportState
    timeline: list[CaseEvent]
    headline: CaseHeadline           # {elapsed_min, projected_total_min, saved_vs_baseline_min, text}
```

Also: `Facility` (§11), `TransportAsset {id, mode, home_facility_id, status: available|busy|offline, crew_note}`, `HospitalCapacity {facility_id, icu_beds_free, cath_lab_available, ct_available, blood_bank_units, updated_at}`, `DemoState {clock_offset_min, speed_multiplier, weather: {sea_state 0–9, wind_kt, visibility_km}, night_override: bool | None}`.

### 6.3 Database (TimescaleDB / Tiger Cloud) — `engine/app/migrations/001_init.sql`

```sql
CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE cases (
  id UUID PRIMARY KEY, short_code TEXT UNIQUE NOT NULL,
  created_at TIMESTAMPTZ NOT NULL, updated_at TIMESTAMPTZ NOT NULL,
  status TEXT NOT NULL, origin_facility_id TEXT NOT NULL,
  patient JSONB NOT NULL, intake JSONB, news2 JSONB, recommendation JSONB,
  referral JSONB, transport JSONB NOT NULL DEFAULT '{"status":"none"}'
);

CREATE TABLE vitals_readings (
  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL, id UUID NOT NULL, source TEXT NOT NULL,
  heart_rate REAL, resp_rate REAL, spo2 REAL, on_oxygen BOOLEAN, systolic_bp REAL,
  temperature_c REAL, consciousness TEXT, confidence REAL, media_url TEXT,
  PRIMARY KEY (case_id, recorded_at, id)
);
SELECT create_hypertable('vitals_readings', 'recorded_at', if_not_exists => TRUE);

CREATE TABLE transport_positions (
  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  recorded_at TIMESTAMPTZ NOT NULL, asset_id TEXT, leg_index INT,
  lat DOUBLE PRECISION NOT NULL, lng DOUBLE PRECISION NOT NULL, speed_kmh REAL,
  PRIMARY KEY (case_id, recorded_at)
);
SELECT create_hypertable('transport_positions', 'recorded_at', if_not_exists => TRUE);

CREATE TABLE case_events (
  case_id UUID NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  at TIMESTAMPTZ NOT NULL, id UUID NOT NULL, type TEXT NOT NULL,
  actor_role TEXT NOT NULL, summary TEXT NOT NULL, data JSONB NOT NULL DEFAULT '{}',
  PRIMARY KEY (case_id, at, id)
);
SELECT create_hypertable('case_events', 'at', if_not_exists => TRUE);

CREATE TABLE transport_assets (id TEXT PRIMARY KEY, mode TEXT NOT NULL, home_facility_id TEXT NOT NULL, status TEXT NOT NULL, crew_note TEXT);
CREATE TABLE hospital_capacity (facility_id TEXT PRIMARY KEY, icu_beds_free INT, cath_lab_available BOOLEAN, ct_available BOOLEAN, blood_bank_units INT, updated_at TIMESTAMPTZ NOT NULL);
CREATE TABLE demo_state (id INT PRIMARY KEY DEFAULT 1, state JSONB NOT NULL);

-- 1-minute vitals buckets for trend charts & forecasting (F-M7.2)
CREATE MATERIALIZED VIEW vitals_1m WITH (timescaledb.continuous) AS
SELECT case_id, time_bucket('1 minute', recorded_at) AS bucket,
       avg(heart_rate) AS hr, avg(resp_rate) AS rr, avg(spo2) AS spo2,
       avg(systolic_bp) AS sbp, avg(temperature_c) AS temp, count(*) AS n
FROM vitals_readings GROUP BY case_id, bucket WITH NO DATA;
SELECT add_continuous_aggregate_policy('vitals_1m',
  start_offset => INTERVAL '1 day', end_offset => INTERVAL '1 minute', schedule_interval => INTERVAL '1 minute');
```

- Migrations run on engine startup, idempotently (track applied files in a `schema_migrations` table). **Never drop tables** in migrations; `/demo` reset deletes rows only.
- Facilities stay in `facilities.json` (static reference data), not the DB.
- Trend endpoint should query `vitals_1m` with `real-time aggregation` fallback to raw rows if the view is empty (cases are minutes old during the demo).

---

## 7. API (FastAPI, prefix `/api`)

All responses JSON; errors `{ "error": { "code": str, "message": str } }`. All mutations append a `CaseEvent` and return the full updated `Case`.

| Method | Path | Body → Returns | Feature |
|---|---|---|---|
| GET | `/api/meta` | → `{facilities, transport_modes, conditions, adapters: {presage, gemini, elevenlabs, storage: "real"|"mock"}, demo_state, now}` | F-M7.5 |
| GET | `/api/cases?status=&destination_id=&origin_id=` | → `CaseListItem[]` (id, short_code, status, severity, origin, destination, headline, updated_at) | F-M3.1 |
| POST | `/api/cases` | `{origin_facility_id, patient?, raw_text?}` → `Case` | F-M1.1 |
| GET | `/api/cases/{id}` | → `Case` | all |
| PATCH | `/api/cases/{id}` | partial `{patient?, origin_facility_id?}` → `Case` | F-M1.3 |
| POST | `/api/cases/{id}/submit` | → `Case` (status submitted, triggers intake + assess) | F-M1.5 |
| POST | `/api/cases/{id}/intake` | `{raw_text, language?}` → `Case` (Gemini extraction) | F-M2.2 |
| POST | `/api/cases/{id}/vitals` | `VitalsReading` (manual) → `Case` (recomputes NEWS2 + re-assesses) | F-M6.3 |
| POST | `/api/cases/{id}/vitals/scan` | multipart `video` (webm/mp4, ≤30 s) → `{job_id}` | F-M6.1 |
| GET | `/api/vitals/scan/{job_id}` | → `{status: queued|processing|done|failed, reading?: VitalsReading, error?}` | F-M6.2 |
| GET | `/api/cases/{id}/vitals/trend?window_min=60` | → `{buckets: [{t, hr, rr, spo2, sbp, temp, news2}]}` | F-M2.6 |
| POST | `/api/cases/{id}/assess` | → `Case` (re-run engine: news2 → conditions → routing → decision → forecast → baseline) | F-M2.1 |
| GET | `/api/cases/{id}/routes` | → `RouteOption[]` (all, incl. infeasible with reasons) | F-M2.5 |
| POST | `/api/cases/{id}/refer` | `{destination_id?, route_id?, note?}` → `Case` (generates SBAR, status referred) | F-M1.6 |
| POST | `/api/cases/{id}/referral/respond` | `{response: accepted|declined|needs_info, responder_name, note?, info_requests?}` → `Case` (decline triggers re-plan F-M3.5) | F-M3.3 |
| POST | `/api/cases/{id}/referral/info` | `{answers: {question: answer}}` → `Case` | F-M3.4 |
| POST | `/api/cases/{id}/dispatch` | `{route_id, asset_ids?}` → `Case` (starts simulator) | F-M4.2 |
| GET | `/api/cases/{id}/track` | → `{positions: [{t, lat, lng, leg_index}], transport: TransportState}` | F-M4.3 |
| POST | `/api/cases/{id}/arrive` | → `Case` | F-M4.5 |
| POST | `/api/cases/{id}/close` | `{outcome_note}` → `Case` | F-M3.7 |
| POST | `/api/cases/{id}/notes` | `{text, actor_role}` → `Case` | F-M3.6 |
| POST | `/api/voice/transcribe` | multipart `audio`, `language?` → `{text, language, confidence}` | F-M5.1 |
| POST | `/api/voice/speak` | `{text, voice?: "guide"|"status", language?}` → `{audio_url}` (cached by hash) | F-M5.2 |
| GET | `/api/cases/{id}/guidance` | → `{steps: [{id, text, audio_url?}], source_condition_id, disclaimer}` | F-M5.3 |
| GET | `/api/hospitals/capacity` | → `HospitalCapacity[]` | F-M3.8 |
| PATCH | `/api/hospitals/{facility_id}/capacity` | partial capacity → `HospitalCapacity` (re-assesses open cases) | F-M3.8 |
| GET | `/api/transport/assets` | → `TransportAsset[]` | F-M4.6 |
| PATCH | `/api/transport/assets/{id}` | `{status}` → `TransportAsset` | F-M4.6 |
| GET/PATCH | `/api/demo/state` | `DemoState` | F-M8.2 |
| POST | `/api/demo/reset` | → `{ok}` (truncate case rows, reseed assets/capacity) | F-M8.1 |
| POST | `/api/demo/scenario/{scenario_id}` | → `Case` (creates and plays a scripted case) | F-M8.3 |
| GET | `/api/media/{key}` | streams local storage file (when storage=local) | F-M7.4 |
| GET | `/api/health` | → `{ok, db, adapters}` | F-M7.5 |

Re-assessment is triggered automatically after: intake, vitals, capacity change, asset status change, demo state change, decline. Debounce per case: max once per 2 s.

---

## 8. Decision engine specification (Module M2 — the technical core)

Pipeline (`core/decision.py::assess(case, ctx) -> Recommendation`):

```
Intake (Gemini) ─┐
Vitals ──► NEWS2 ├─► Severity ─► Condition & window ─► Candidate routes (routing) ─► Score & choose ─► Explain (Gemini)
Capacity/assets/clock/weather ─────────────────────────────┘                              │
                                                       Forecast (Timescale trend) ────────┤
                                                       Baseline comparison ───────────────┘
```

Everything here is **deterministic and unit-tested** except the Gemini steps, which have deterministic fallbacks.

### 8.1 F-M2.2 Structured intake (Gemini)

- Input: free text (typed or transcribed), patient fields, origin, current time.
- Call Gemini via `google-genai` with `response_mime_type="application/json"` and `response_schema` = the `Intake` schema (minus `raw_text`, `extracted_by`). Model from `GEMINI_MODEL` env (default `gemini-flash-latest`; team verifies current model id on ai.google.dev).
- System prompt must: restrict `suspected_conditions[].condition_id` to IDs in `conditions.yaml` (pass the list) plus `"other"`; require probabilities that sum ≤ 1; convert relative onset ("2 hours ago") to an absolute ISO time using the supplied current time; output `missing_info` as short clinician questions; never give treatment advice.
- Validate with Pydantic; on failure retry once, then fall back to `fallback_intake.py` (keyword → condition map, e.g. "chest pain|crushing|left arm|sweating" → `stemi`), `extracted_by="fallback_rules"`.
- Timeout 12 s. Language: accept English + any language Gemini handles; store detected `language`.

### 8.2 F-M2.3 NEWS2 (Royal College of Physicians, SpO₂ Scale 1)

| Parameter | 3 | 2 | 1 | 0 | 1 | 2 | 3 |
|---|---|---|---|---|---|---|---|
| Resp rate /min | ≤8 | | 9–11 | 12–20 | | 21–24 | ≥25 |
| SpO₂ % | ≤91 | 92–93 | 94–95 | ≥96 | | | |
| Air or oxygen | | Oxygen | | Air | | | |
| Systolic BP | ≤90 | 91–100 | 101–110 | 111–219 | | | ≥220 |
| Pulse /min | ≤40 | | 41–50 | 51–90 | 91–110 | 111–130 | ≥131 |
| Consciousness | | | | A | | | C/V/P/U = 3 |
| Temperature °C | ≤35.0 | | 35.1–36.0 | 36.1–38.0 | 38.1–39.0 | ≥39.1 (=2) | |

- Bands: total 0–4 → `low`; any single parameter = 3 (and total ≤4) → `low_medium`; 5–6 → `medium`; ≥7 → `high`.
- Uses the **latest non-null value per parameter within the last 30 min** (sim clock). Missing parameters → `complete=false`, list them in `missing`, compute partial total; UI shows "Partial NEWS2 (HR, RR only)". Presage gives HR + RR only — this is expected and the UI must prompt for SpO₂/BP/consciousness/temp when a clinician is present.
- Severity mapping: `high` → `high`; plus any red flag from a time-critical condition with probability ≥ 0.4 → `critical`; partial NEWS2 never downgrades severity implied by red flags.
- Unit tests: every boundary value in the table.

### 8.3 F-M2.4 Conditions, time windows, required capabilities — `data/conditions.yaml`

> DEMO ASSUMPTION — illustrative clinical reference values; not medical advice.

| condition_id | Label | Window (from) | Window | Definitive care requires | Interim option if window can't be met |
|---|---|---|---|---|---|
| `stemi` | Heart attack (STEMI) | first medical contact | 120 min to PCI | `cath_lab` | Fibrinolysis at facility with `thrombolysis` within 30 min, then transfer |
| `stroke` | Stroke | symptom onset | 270 min (4.5 h) to thrombolysis | `ct`, `thrombolysis` | — (flag breach) |
| `major_trauma` | Major trauma / severe bleeding | injury | 60 min to surgery (golden hour) | `surgery`, `blood_bank` | Damage-control at nearest `surgery` facility |
| `pph` | Postpartum haemorrhage | onset | 30 min to obstetric surgery/blood | `obstetric_surgery`, `blood_bank` | Nearest facility with `blood_bank` |
| `sepsis` | Sepsis | recognition | 60 min to IV antibiotics | `iv_antibiotics` | Start at health centre (health centres have it) |
| `respiratory_failure` | Severe breathing difficulty | recognition | 60 min to ventilatory support | `icu` | Nearest `icu` |
| `appendicitis` | Suspected appendicitis | recognition | 1440 min | `surgery` | — |
| `other` | Undifferentiated | — | none | by severity: high → `icu`, else `general` | — |

Selection: `primary_condition` = highest probability × (time-critical weight 1.5 if window ≤ 120 min). Window clock starts from `onset_time` (or case `created_at` if unknown, with `onset_confidence="unknown"` shown in UI as a warning). Destination candidates = facilities whose `capabilities` ⊇ required **and** whose live capacity allows it (`cath_lab_available`, `icu_beds_free > 0`, `ct_available`).

### 8.4 F-M2.5 Routing — `core/routing.py`

Model the archipelago as a graph of **facility nodes** (islands with health centres, hospitals, airports) from `facilities.json`. Distances: haversine × `detour_factor` (sea 1.25, air 1.05, ground 1.0).

`transport_modes.yaml` (DEMO ASSUMPTION):

| mode | speed km/h | dispatch_min | handover_min | constraints |
|---|---|---|---|---|
| ground | 30 | 5 | 5 | same island only, or `hulhule ↔ male` (bridge, 15 km/h effective) |
| speedboat | 45 | 15 | 10 | any island↔island; disabled if sea_state ≥ 5; speed ×0.8 if sea_state 4 |
| sea_ambulance | 37 | 25 | 10 | any island↔island; disabled if sea_state ≥ 6; has medic onboard (+score) |
| seaplane | 280 | 45 | 15 | lands at any lagoon; **daylight only** (local sunrise 06:00 – sunset 18:15, minus 60 min before sunset for the return), disabled if wind_kt ≥ 25 or visibility_km < 5 |
| fixed_wing | 450 | 60 | 20 | airport ↔ airport only; night allowed; disabled if visibility_km < 2 |
| helicopter | 220 | 30 | 10 | disabled by default (`enabled: false`), toggle in /demo |

Dispatch time only applies to the **first** leg of each asset; uses the nearest *available* asset of that mode (`transport_assets`); if none available, mode is infeasible with reason "no available <mode>".

**Route templates enumerated per candidate destination D** (origin O):
1. `O ─sea→ D` (speedboat, sea_ambulance)
2. `O ─seaplane→ D` (if D has lagoon access; IGMH via Hulhulé seaplane base + ground leg)
3. `O ─sea→ A1 ─fixed_wing→ A2 ─(ground|sea)→ D` where A1 = nearest airport to O (A1 may be O itself), A2 = nearest airport to D
4. **Interim-stop plans**: `O → H_interim (stabilise, +stabilise_min from conditions.yaml, default 30) → D` for conditions with an interim option; the window check uses the time to *interim care* for the interim treatment and full time to D for definitive care.

For each route compute legs with `depart_at/arrive_at` on the sim clock (respecting daylight constraints at the *departure time of each leg*), `total_min`, feasibility, reasons. Return all, including infeasible.

### 8.5 F-M2.5 Scoring & choice — `core/decision.py`

```
score = total_min
      + 0.0                       if within_window else  3 * (total_min - window_min)     # breach penalty
      - 10 if mode includes sea_ambulance or medic onboard and severity ≥ high
      + 15 per extra handover beyond 2
      + 1000 if not feasible
```
- Choose min score among feasible routes. If **no** route reaches definitive care within the window: choose best interim-stop plan if one meets the *interim* window; set `breach_warning` (e.g. "No route reaches PCI within 120 min. Recommended: fibrinolysis at Gan Regional (ETA 48 min), then fixed-wing to Malé.").
- `alternatives`: top 3 by score (always include the chosen one) for the UI comparison.
- `actions_now`: from `first_aid.yaml` for `primary_condition` × role (reporter vs clinician) — vetted text only.
- Re-plan on decline (exclude declined destination), capacity change, asset change, weather/clock change.

### 8.6 F-M2.6 Deterioration forecast (Tiger Data trend)

- Pull `vitals_1m` buckets for the case (fallback raw). Compute NEWS2 per bucket.
- Fit ordinary least squares on (minutes, NEWS2) over the last ≤ 60 min with ≥ 3 points; also per-parameter slopes for HR and RR.
- Output `DeteriorationForecast { slope_per_hour, projected_news2_at_arrival, minutes_to_news2_7 | None, trend: "improving"|"stable"|"worsening", confidence: "low"|"medium" (≥6 points & R²≥0.5) }`.
- If projected NEWS2 at arrival ≥ 7 and the chosen route has no medic onboard → add warning and prefer `sea_ambulance`/medic routes (+ re-score).
- UI copy is always hedged: "Trend suggests…", with the number of points used.

### 8.7 F-M2.7 SBAR referral summary · F-M2.8 Explanation (Gemini)

- **SBAR**: Gemini generates `SbarSummary` from case JSON (patient, intake, vitals, NEWS2, recommendation). Prompt: factual, ≤ 120 words total, no fabricated values — only use fields provided; mark unknowns as "not recorded". Fallback: string template.
- **Explanation**: ≤ 3 sentences explaining why the chosen route beats the alternatives, citing numbers from the routes JSON (e.g. "Seaplane is unavailable at night; fixed-wing from Kadhdhoo reaches IGMH 2 h 40 min sooner than sea ambulance."). Fallback: template from the top-2 route diff.
- All Gemini outputs are cached on the case and regenerated only when inputs change (hash of inputs).

### 8.8 F-M2.9 Baseline comparison (headline metric)

`data/baseline.yaml` — DEMO ASSUMPTION durations of the **sequential phone chain**:

```yaml
steps:
  - {id: reach_health_centre, label: "Patient reaches health centre", min: 0}   # same in both (we start at alert)
  - {id: call_regional, label: "Health centre calls atoll/regional hospital", min: 20}
  - {id: call_specialist, label: "Regional calls specialist in Malé", min: 40}
  - {id: approval, label: "Evacuation approval & funding confirmation", min: 60}
  - {id: arrange_transport, label: "Transport operator found & arranged", min: 45}
  - {id: transport, label: "Transport (same route as recommended, no parallelism)", min: "route.total_min"}
ours_parallel_overhead_min: 10   # referral + acceptance in our system (measured from events when available)
```
- `baseline_total = sum(steps)`; `ours_total = measured (accept_at − submit_at, or 10 if pending) + chosen route total_min`.
- `saved_vs_baseline_min = baseline_total − ours_total`. Show both as a stacked horizontal bar on the case page (F-M3.9) with an "Assumptions" popover listing the YAML values.

### 8.9 Engine tests (must pass)
- NEWS2 boundaries (every cell), partial scoring.
- Routing: night disables seaplane; sea_state 6 disables both sea modes; airport chain created only when both ends have airports.
- Decision: scenario `laamu_stemi_night` → chooses interim fibrinolysis at Gan + fixed-wing to IGMH; scenario `daytime_trauma` → seaplane to IGMH.
- Fallback intake detects STEMI from "crushing chest pain left arm sweating".

---

## 9. Feature specification by module

> Format: **F-ID — Name** `priority` · description · **Acceptance criteria (AC)**

### M1 — Island Reporter App (`/report`) · Lane B

**F-M1.1 — One-tap alert** `P0`
Mobile-first page with a giant "Raise medical alert" button, origin island selector (searchable, default from `localStorage`), optional patient name/age/sex. Creates a case (`POST /api/cases`) and routes to `/report/[caseId]`.
AC: case created in < 1 s with mocks; short code (e.g. `AL-4F2K`) shown in large type to read over the phone.

**F-M1.2 — Describe what's happening (text or voice)** `P0`
Textarea + "Hold to speak" (`VoiceRecorder`, F-M5.1). Transcribed text appears editable. "Analyse" calls `/intake`.
AC: after analyse, structured chips appear: chief complaint, red flags (red pills), suspected conditions with probability bars, and "Questions to answer" (`missing_info`) as quick-answer inputs that append to raw text and re-run intake.

**F-M1.3 — Patient details** `P1`
Collapsible form: age, sex, pregnant, known conditions, meds, allergies (tag inputs). PATCH on blur.
AC: changes reflected in SBAR on next generation.

**F-M1.4 — Vitals capture** `P0`
Tabs: **Camera scan** (F-M6.1) | **Enter manually** (`ManualVitalsForm`: HR, RR, SpO₂, on O₂, SBP, temp, ACVPU). NEWS2 card updates live with component breakdown and "Partial" badge.
AC: manual entry of RR 26, SpO₂ 90, SBP 88, HR 135, temp 39.5, V → NEWS2 = 3+3+3+3+2+3 = 17, band high.

**F-M1.5 — Submit & see recommendation** `P0`
"Send to doctor" → `/submit`. Shows severity banner, `RouteCard` (chosen route, legs with mode icons, ETA, window margin), breach warning if any, explanation text, alternatives (expandable), headline metric.
AC: recommendation visible within 3 s (mocks) / 15 s (real Gemini).

**F-M1.6 — Clinician referral** `P0`
When role = island clinician: "Send referral to <destination>" button (destination override dropdown limited to capable facilities). Shows SBAR preview before sending; editable note.
AC: status → `referred`; case appears in `/hospital` inbox for that destination within one poll cycle.

**F-M1.7 — First-aid guidance with voice** `P0`
Card "What to do now" listing `actions_now`/`guidance` steps; each step has ▶ play (ElevenLabs, F-M5.2); "Read all" plays sequentially. Persistent disclaimer: "Guidance support only — follow your clinician's instructions."
AC: works in mock mode (browser `speechSynthesis` fallback) and real mode (ElevenLabs audio).

**F-M1.8 — Live status for family** `P1`
Status stepper (submitted → referred → accepted → dispatched → in transit → arrived), ETA countdown, "Speak update" button that plays an ElevenLabs status sentence. Shareable read-only link `/case/[caseId]` with QR code.
AC: stepper advances automatically via polling.

**F-M1.9 — Respond to info requests** `P1`
If specialist sets `needs_info`, a highlighted panel lists the questions with inputs; submit → `/referral/info`.
AC: specialist sees answers in their case view.

**F-M1.10 — Offline-tolerant draft** `P2`
Unsent text/vitals stored in `localStorage` per case; banner "Offline — will send when connected"; retry queue on `online` event.
AC: toggling DevTools offline and back sends the queued vitals.

### M2 — Decision Engine · Lane A
(F-M2.1 orchestrator `P0`, F-M2.2 intake `P0`, F-M2.3 NEWS2 `P0`, F-M2.4 conditions `P0`, F-M2.5 routing+decision `P0`, F-M2.6 forecast `P1`, F-M2.7 SBAR `P0`, F-M2.8 explanation `P1`, F-M2.9 baseline `P0` — all fully specified in §8.)

**F-M2.10 — Engine inspector** `P1`
`/hospital/[caseId]` (and `/demo`) has an "Engine details" drawer: NEWS2 component table, condition probabilities, every route incl. infeasible with reasons, score breakdown, Gemini vs fallback badges, input hash.
AC: judges can see *why* a route was rejected ("seaplane: after sunset 18:15").

### M3 — Hospital / Specialist Dashboard (`/hospital`) · Lane C

**F-M3.1 — Referral inbox** `P0`
Facility selector (default IGMH). Table/cards of incoming cases sorted by severity then window margin: short code, severity pill, condition, origin island, time since onset, window remaining (red when < 30 min), status pill, ETA.
AC: new referral appears within 2 s; critical cases pulse (CSS keyframes) for 10 s on arrival.

**F-M3.2 — Case review** `P0`
`/hospital/[caseId]`: SBAR card, intake chips, NEWS2 card, `VitalsChart` (Recharts; HR, RR, SpO₂ lines from `/vitals/trend`), forecast line (dashed) with hedged copy, route card + map preview, timeline.
AC: all panels render with partial data (no vitals, no intake) without crashing.

**F-M3.3 — Accept / Decline / Request info** `P0`
Three buttons; accept requires responder name (remembered); decline requires reason; needs-info opens a modal with suggested questions (pre-filled from `intake.missing_info`) + custom.
AC: accept → status `accepted` and transport page lists the case as ready to dispatch; decline → `replanned` event, new destination chosen and referral re-sent automatically to it.

**F-M3.4 — Info Q&A thread** `P1`
Shows info requests and island answers in order.

**F-M3.5 — Auto re-plan on decline** `P0` (engine + UI toast "Re-routed to Hithadhoo Regional: IGMH cath lab unavailable").

**F-M3.6 — Case notes** `P2` — free-text notes by any role into timeline.

**F-M3.7 — Close case** `P1` — outcome note; shows final total time vs baseline.

**F-M3.8 — Capacity panel** `P1`
Per facility: ICU beds free, cath lab available toggle, CT toggle, blood units. Changing it re-assesses open cases (visible re-plan).
AC: toggling IGMH cath lab off during the STEMI scenario changes the recommendation within 2 s.

**F-M3.9 — Time-saved panel** `P0` — stacked bar: baseline steps vs ours, total saved, assumptions popover (F-M2.9).

### M4 — Transport Coordination (`/transport`) · Lane C

**F-M4.1 — Dispatch board** `P0`
Columns: *Ready to dispatch* (accepted), *In transit*, *Arrived today*. Each card: route legs, assets needed, ETA, window margin.

**F-M4.2 — Dispatch** `P0`
Select route (defaults to chosen; alternatives selectable) and assets (auto-picked nearest available, overridable) → `/dispatch`. Assets become `busy`.
AC: status → `dispatched` then `in_transit` once simulator starts the first leg.

**F-M4.3 — Live map** `P0`
`AtollMap` (react-leaflet, OSM tiles or CARTO light/dark tiles matching theme): all facilities (icons by type: health centre, hospital, airport), case origin, destination, planned route polyline (dashed per leg, coloured by mode), live asset marker interpolated between polled positions, trail from `transport_positions`.
AC: map renders on mobile width; marker moves smoothly during demo at speed multiplier 60×.

**F-M4.4 — Transport simulator** `P0`
Engine background task: for each in-transit case, every 2 s (real) advance along legs according to sim clock & leg speeds, write a `transport_positions` row, emit `departed`/`leg_completed`/`arrived` events, update ETA. Interim stops pause for `stabilise_min`.
AC: survives engine restart (state rebuilt from DB).

**F-M4.5 — Arrival & handover** `P0` — auto on sim arrival or manual "Mark arrived"; destination hospital sees "Arrived".

**F-M4.6 — Asset roster** `P1` — list of assets with status toggles (available/busy/offline); setting the only seaplane offline triggers re-plan for non-dispatched cases.

**F-M4.7 — Weather & daylight banner** `P1` — current sim time, sunrise/sunset, sea state, wind, visibility, with which modes are currently disabled and why.

**F-M4.8 — Crew audio brief** `P2` — "Play crew brief": ElevenLabs reads a short SBAR-derived brief for the boat crew.

### M5 — Voice (ElevenLabs) · Lane A (backend) / B (frontend)

**F-M5.1 — Speech-to-text intake** `P0` — `VoiceRecorder` uses `MediaRecorder` (webm/opus), uploads to `/api/voice/transcribe` → ElevenLabs Speech-to-Text (`ELEVENLABS_STT_MODEL`, default `scribe_v1`; verify current id). Mock: returns scenario text. Language hint optional.

**F-M5.2 — Text-to-speech** `P0` — `/api/voice/speak` → ElevenLabs TTS (`ELEVENLABS_TTS_MODEL`, default `eleven_multilingual_v2`; two voice IDs from env: calm "guide", crisp "status"). Cache MP3 by sha256(text+voice+model) in object storage. Mock/failed: return `{audio_url: null}` and the frontend uses `window.speechSynthesis`.

**F-M5.3 — Guidance library** `P0` — `first_aid.yaml`: per condition × role, 3–6 short vetted steps (e.g. STEMI reporter: "Keep them seated and calm", "Loosen tight clothing", "If they become unresponsive and aren't breathing normally, start chest compressions"). Gemini may only **select and order** step IDs, never write new medical instructions.

**F-M5.4 — Language support** `P2` — language selector (English default; additional languages listed from config). Dhivehi: show "Voice not yet available — text only" unless the team confirms ElevenLabs support (do not claim support).

### M6 — Contactless Vitals (Presage) · Lane A (adapter) / B (frontend)

**F-M6.1 — Camera scan UI** `P0`
`CameraScan`: `getUserMedia` front/back camera toggle, face-framing oval overlay, lighting tips, 30 s countdown ring, record via `MediaRecorder`, upload to `/vitals/scan`.
AC: works on mobile Chrome/Safari over HTTPS; permission denial shows manual-entry fallback.

**F-M6.2 — Scan processing** `P0`
Engine `PresageAdapter.process(video_path) -> VitalsReading`. Modes:
- `sdk` — call SmartSpectra (Linux) via subprocess/binding; `TODO(presage-verify)`.
- `cloud` — POST to Presage endpoint with `PRESAGE_API_KEY`; `TODO(presage-verify)`.
- `mock` — returns plausible values with small noise (scenario-driven, e.g. HR 112 ± 3, RR 24 ± 1), confidence 0.9, after a 3 s delay.
- `manual` — scan disabled; UI goes straight to manual form.
Job runs in background; frontend polls `/vitals/scan/{job}`. Video stored in object storage (`media_url`), deleted after 24 h (lifecycle note in README).
AC: result card shows HR, RR, confidence, "Source: Presage" pill, and feeds NEWS2.

**F-M6.3 — Continuous monitoring mode** `P1` — "Monitor" toggle repeats a scan every 2 min (or sim-accelerated) producing a trend; each result POSTs a reading.

**F-M6.4 — Quality gating** `P1` — readings with confidence < 0.6 are stored but flagged and excluded from NEWS2, UI prompts rescan.

### M7 — Platform & Infrastructure · Shared

**F-M7.1 — Local dev** `P0` — `docker compose up` starts `timescale/timescaledb:latest-pg16`, engine (uv, hot reload), web (bun dev). Works with no keys.
**F-M7.2 — Tiger Data** `P0` — `DATABASE_URL` may point to Tiger Cloud; migrations from §6.3 run idempotently; README explains creating the Tiger Cloud service.
**F-M7.3 — Vultr deploy** `P0` — `docker-compose.prod.yml` + `Caddyfile` (domain via `PUBLIC_HOST`, supports `<ip>.sslip.io` for instant HTTPS), `scripts/deploy_vultr.sh` (rsync/git pull + compose up). README: create Ubuntu Cloud Compute instance, open 80/443, set env.
**F-M7.4 — Object storage** `P1` — `StorageAdapter`: `s3` (Vultr Object Storage via boto3, `S3_ENDPOINT`, bucket, keys; presigned GET URLs) | `local` (`./var/storage`, served by `/api/media/{key}`).
**F-M7.5 — Health & adapter status** `P0` — `/api/health`; footer shows adapter pills ("Gemini: live", "Presage: mock").
**F-M7.6 — Type generation** `P0` — `bun run gen:api` → `web/src/lib/api-types.ts` from engine OpenAPI; committed.
**F-M7.7 — Error handling** `P0` — global FastAPI exception handler; frontend toast on error; every adapter failure degrades to fallback with a timeline `note` event ("Gemini timed out — used rule-based intake").
**F-M7.8 — Logging** `P2` — structured JSON logs with case_id.

### M8 — Demo Control (`/demo`) · Lane C

**F-M8.1 — Reset** `P0` — wipes case data, reseeds assets & capacity.
**F-M8.2 — World controls** `P0` — sim clock (set time of day; quick buttons "Day 14:00", "Night 21:00"), speed multiplier (1×, 10×, 60×, 300×), sea state, wind, visibility, helicopter toggle.
**F-M8.3 — Scenarios** `P0` — buttons to load each scenario in §12; a scenario creates the case, posts scripted intake text and vitals at scripted sim times, optionally auto-advances (auto-refer, auto-accept after N s) via a "Autoplay" checkbox.
**F-M8.4 — Presenter view** `P1` — split screen (`/demo?view=split`): phone frame (report page iframe) + hospital + map side by side for the stage screen.

### M9 — Docs & Pitch · Shared

**F-M9.1 — README** `P0` — what it is, architecture diagram, run locally, env vars, deploy, track mapping.
**F-M9.2 — PITCH.md** `P0` — 3-minute demo script (§12.1) and judge Q&A prep (safety, data, scale, why not just WhatsApp).
**F-M9.3 — DEV_POST.md** `P1` — draft blog post: problem, build, tech per sponsor, challenges, what's next.
**F-M9.4 — FEATURES.md / KNOWN_ISSUES.md** `P0` — see §0.6.

### M10 — Landing & Shared UI · Shared

**F-M10.1 — Landing page** `P1` — `/`: one-paragraph problem, the headline metric from the last closed demo case, three big role entry cards (Island / Hospital / Transport), sponsor tech strip.
**F-M10.2 — Header** `P0` — fixed, scroll-aware, logo, nav (Report, Hospital, Transport, Demo), role switcher, theme toggle; mobile hamburger with max-height transition.
**F-M10.3 — Case timeline** `P0` — vertical timeline of `CaseEvent`s with relative + absolute times (sim clock), actor role icons, durations between key events.
**F-M10.4 — Dark mode** `P1` — system default + toggle.

---

## 10. UX & visual design

- **Feel:** calm, clinical, high-contrast, fast. This is an emergency tool — no decoration, no gradients, no blobs, no emojis.
- **Colours (max 5):** neutral white/black, neutral greys, **primary ocean teal** `#0E7C86` (brand), **alert red** `#D92D20` (critical/breach only), **amber** `#F79009` (warnings/medium). Severity: low = neutral, low_medium/medium = amber, high/critical = red.
- **Type:** one family — Inter (or Geist) for everything; tabular numerals for vitals/ETAs. Min text 14px; inputs 16px.
- **Touch targets** ≥ 44px; the alert button is ≥ 30% of viewport height on mobile.
- **Icons:** `lucide-react` only, sizes 16/20/24. Mode icons: ship (speedboat), ambulance (sea_ambulance), plane (fixed_wing), plane-landing (seaplane), car (ground).
- **Numbers first:** ETAs, window remaining, NEWS2 are the largest elements in their cards.
- **Every AI output is badged** ("AI-generated · Gemini" or "Rule-based fallback") and every assumption is labelled ("DEMO ASSUMPTION").
- Loading states: skeletons with a subtle pulse keyframe; never a blank page.
- Mobile-first for `/report` and `/case`; desktop-first (but responsive) for `/hospital`, `/transport`, `/demo`.

---

## 11. Seed data — `engine/app/data/facilities.json`

> DEMO ASSUMPTION — coordinates approximate, capabilities illustrative. Verify before claiming in the pitch.

```jsonc
[
  // Malé region
  {"id":"igmh","name":"Indira Gandhi Memorial Hospital (Malé)","type":"tertiary_hospital","atoll":"Kaafu","lat":4.1755,"lng":73.5093,
   "capabilities":["general","iv_antibiotics","icu","ct","thrombolysis","cath_lab","surgery","obstetric_surgery","blood_bank"],"has_airport":false,"nearest_airport_id":"hulhule","lagoon_access":true},
  {"id":"hulhule","name":"Velana Intl Airport (Hulhulé) + seaplane base","type":"airport","atoll":"Kaafu","lat":4.1918,"lng":73.5291,"capabilities":[],"has_airport":true},
  // Regional / atoll hospitals
  {"id":"gan_l_rh","name":"Gan Regional Hospital (Laamu)","type":"regional_hospital","atoll":"Laamu","lat":1.9300,"lng":73.5420,
   "capabilities":["general","iv_antibiotics","thrombolysis","surgery","obstetric_surgery","blood_bank"],"nearest_airport_id":"kadhdhoo","lagoon_access":true},
  {"id":"kadhdhoo","name":"Kadhdhoo Airport (Laamu)","type":"airport","atoll":"Laamu","lat":1.8592,"lng":73.5219,"has_airport":true},
  {"id":"hithadhoo_rh","name":"Hithadhoo Regional Hospital (Addu)","type":"regional_hospital","atoll":"Seenu","lat":-0.6050,"lng":73.0900,
   "capabilities":["general","iv_antibiotics","icu","ct","thrombolysis","surgery","obstetric_surgery","blood_bank"],"nearest_airport_id":"gan_addu","lagoon_access":true},
  {"id":"gan_addu","name":"Gan International Airport (Addu)","type":"airport","atoll":"Seenu","lat":-0.6933,"lng":73.1556,"has_airport":true},
  {"id":"kulhudhuffushi_rh","name":"Kulhudhuffushi Regional Hospital","type":"regional_hospital","atoll":"Haa Dhaalu","lat":6.6224,"lng":73.0700,
   "capabilities":["general","iv_antibiotics","icu","ct","thrombolysis","surgery","obstetric_surgery","blood_bank"],"has_airport":true,"lagoon_access":true},
  {"id":"eydhafushi_ah","name":"Baa Atoll Hospital (Eydhafushi)","type":"atoll_hospital","atoll":"Baa","lat":5.1036,"lng":73.0702,
   "capabilities":["general","iv_antibiotics","surgery","blood_bank"],"nearest_airport_id":"dharavandhoo","lagoon_access":true},
  {"id":"dharavandhoo","name":"Dharavandhoo Airport (Baa)","type":"airport","atoll":"Baa","lat":5.1561,"lng":73.1302,"has_airport":true},
  {"id":"muli_ah","name":"Meemu Atoll Hospital (Muli)","type":"atoll_hospital","atoll":"Meemu","lat":2.9200,"lng":73.5800,
   "capabilities":["general","iv_antibiotics","blood_bank"],"lagoon_access":true},
  {"id":"thinadhoo_rh","name":"Thinadhoo Regional Hospital (Gaafu Dhaalu)","type":"regional_hospital","atoll":"Gaafu Dhaalu","lat":0.5300,"lng":72.9960,
   "capabilities":["general","iv_antibiotics","surgery","obstetric_surgery","blood_bank"],"nearest_airport_id":"kaadedhdhoo","lagoon_access":true},
  {"id":"kaadedhdhoo","name":"Kaadedhdhoo Airport (Gaafu Dhaalu)","type":"airport","atoll":"Gaafu Dhaalu","lat":0.4881,"lng":72.9969,"has_airport":true},
  // Island health centres (origins)
  {"id":"isdhoo_hc","name":"Isdhoo Health Centre (Laamu)","type":"health_centre","atoll":"Laamu","lat":2.1200,"lng":73.5700,"capabilities":["general","iv_antibiotics"],"nearest_airport_id":"kadhdhoo","lagoon_access":true},
  {"id":"dhangethi_hc","name":"Dhangethi Health Centre (Alif Dhaalu)","type":"health_centre","atoll":"Alif Dhaalu","lat":3.6070,"lng":72.9580,"capabilities":["general","iv_antibiotics"],"nearest_airport_id":"maamigili","lagoon_access":true},
  {"id":"maamigili","name":"Maamigili Airport (Alif Dhaalu)","type":"airport","atoll":"Alif Dhaalu","lat":3.4706,"lng":72.8358,"has_airport":true},
  {"id":"dhiffushi_hc","name":"Dhiffushi Health Centre (Kaafu)","type":"health_centre","atoll":"Kaafu","lat":4.4420,"lng":73.7140,"capabilities":["general","iv_antibiotics"],"nearest_airport_id":"hulhule","lagoon_access":true},
  {"id":"vaadhoo_hc","name":"Vaadhoo Health Centre (Gaafu Dhaalu)","type":"health_centre","atoll":"Gaafu Dhaalu","lat":0.2300,"lng":73.2800,"capabilities":["general","iv_antibiotics"],"nearest_airport_id":"kaadedhdhoo","lagoon_access":true},
  {"id":"kendhoo_hc","name":"Kendhoo Health Centre (Baa)","type":"health_centre","atoll":"Baa","lat":5.2700,"lng":73.0200,"capabilities":["general","iv_antibiotics"],"nearest_airport_id":"dharavandhoo","lagoon_access":true}
]
```

Assets (seeded into `transport_assets`): 1 sea ambulance + 1 speedboat at each hospital; 2 seaplanes at `hulhule`; 1 fixed-wing medevac at `hulhule`; 1 speedboat at each health centre. Capacity seeded: all `true`/positive; IGMH ICU 4 beds.

---

## 12. Demo scenarios — `engine/app/data/scenarios/`

| id | Story | What it proves |
|---|---|---|
| `laamu_stemi_night` (**hero**) | 21:00, Isdhoo (Laamu). 58-year-old fisherman, "crushing chest pain for 40 minutes, sweating, pain going to left arm". Presage scan HR 112, RR 24. | Seaplane infeasible (night); sea ambulance to Malé ≈ 6+ h breaches the 120-min PCI window → engine recommends **speedboat to Gan Regional for fibrinolysis + fixed-wing Kadhdhoo → Hulhulé → IGMH for PCI**. Headline time saved. |
| `daytime_trauma` | 11:00, Dhangethi. Fall from coconut tree, open leg fracture, heavy bleeding. HR 128, RR 26, SBP 88. | Seaplane direct to IGMH wins; NEWS2 high; sea-ambulance alternative shown. |
| `stroke_capacity_flip` | 15:00, Kendhoo (Baa). 70-year-old woman, sudden right-sided weakness & slurred speech, onset 50 min ago. | Starts routed to IGMH; presenter toggles IGMH CT off → re-plans to Kulhudhuffushi RH live. |
| `pph_weather` | 17:30, Vaadhoo. Postpartum bleeding. Sea state set to 6 by presenter. | Sea modes disabled, seaplane near sunset cutoff → fixed-wing from Kaadedhdhoo or nearest blood bank; shows constraint reasoning. |
| `sepsis_local` | 09:00, Dhiffushi. Fever, confusion, RR 25, temp 39.4. | IV antibiotics started at health centre (interim within window) + transfer; demonstrates "treat locally first". |

### 12.1 Three-minute pitch flow (write into PITCH.md)
1. (20 s) Problem + map of 190 islands; "the delay isn't medicine, it's handoffs."
2. (60 s) Hero scenario live on a phone: alert → speak symptoms (ElevenLabs STT) → Presage face scan → NEWS2 + Gemini intake → recommendation with *why seaplane is rejected*.
3. (40 s) Switch to hospital screen: SBAR, vitals trend (Tiger Data), one-click accept.
4. (30 s) Transport map: dispatch, boat moving at 60×, spoken status update.
5. (20 s) Headline: "X minutes faster than the phone chain." Architecture strip: Presage · Gemini · ElevenLabs · Tiger Data · Vultr.
6. (10 s) Scale: any archipelago; next steps (real referral data, Dhivehi voice, integration with national systems).

---

## 13. Testing & acceptance

- **Engine (pytest):** §8.9 cases + API smoke tests for every endpoint in mock mode (`TestClient`).
- **E2E script:** `scripts/demo_e2e.py` runs the hero scenario through the API: create → intake → vitals → assess → refer → accept → dispatch → simulate to arrival (speed 300×) → close. Asserts final status `closed` and `saved_vs_baseline_min > 0`.
- **Frontend:** `bun run build` and `bun run lint` pass with zero errors; `bun run typecheck`.
- **Definition of done (whole product):** with `docker compose up` and no API keys, a person can run every scenario in §12 end-to-end through the UI on desktop and on a 375px-wide phone viewport.

---

## 14. Conventions (team standards)

- **JS tooling: bun only** (`bun install`, `bun run`, `bunx`). Python: `uv`.
- Next.js App Router (latest stable), TypeScript strict, Tailwind v4, `tailwind-merge`, `lucide-react`, `swr`, `react-leaflet` + `leaflet`, `recharts`, `qrcode.react`.
- **Tailwind sizes in `rem` arbitrary values only** (`px-[1rem]`, `gap-[.5rem]`), never `px-4` or `px-[16px]`. Borders `border-[1px]`.
- Components: `export default function (...)` with **no function name**; props typed as `React.JSX.IntrinsicElements["div"]` (etc.) spread with `twMerge` for `className`. Base + variant pattern for buttons, pills, modals.
- **Pages are async server components** that render a `Client` component; client logic lives in `*Client.tsx` next to the page.
- Guard clauses over nested `if`s. No single-child wrapper elements unless needed for centring.
- If a component exceeds ~15 Tailwind classes, move styles to a co-located `*.module.scss`.
- Don't use `next/image`; plain `<img>`.
- Python: Pydantic v2, `ruff` formatting, type hints everywhere, no business logic in routers (routers call `core/`).
- Every file implementing a feature starts with its F-ID comment.

## 15. Environment variables — `.env.example`

```bash
# Core
DATABASE_URL=postgresql://postgres:postgres@db:5432/atolllink   # or Tiger Cloud URL (sslmode=require)
PUBLIC_HOST=localhost                                            # Vultr: <ip>.sslip.io or your domain
NEXT_PUBLIC_ENGINE_URL=/api                                      # Caddy proxies /api → engine
CORS_ORIGINS=http://localhost:3000

# Adapters: real | mock (presage: sdk | cloud | mock | manual)
GEMINI_MODE=mock
GEMINI_API_KEY=
GEMINI_MODEL=gemini-flash-latest

ELEVENLABS_MODE=mock
ELEVENLABS_API_KEY=
ELEVENLABS_TTS_MODEL=eleven_multilingual_v2
ELEVENLABS_STT_MODEL=scribe_v1
ELEVENLABS_VOICE_GUIDE=
ELEVENLABS_VOICE_STATUS=

PRESAGE_MODE=mock
PRESAGE_API_KEY=
PRESAGE_SDK_PATH=

STORAGE_MODE=local          # local | s3
S3_ENDPOINT=https://<region>.vultrobjects.com
S3_BUCKET=atolllink
S3_ACCESS_KEY=
S3_SECRET_KEY=

# Demo
DEFAULT_SPEED_MULTIPLIER=1
TIMEZONE=Indian/Maldives
```

---

## 16. Build order (for the agent)

1. Repo skeleton, docker-compose, `.env.example`, engine `config.py`, `models.py`, migrations, `/api/health`, `/api/meta`.
2. `core/` (clock, news2, conditions, routing, decision, baseline, fallback_intake) + **pytest passing**.
3. Adapters with mock modes; then real implementations (Gemini, ElevenLabs, storage S3, Presage best-effort).
4. All routers (§7), simulator, scenarios, demo endpoints. Run `scripts/demo_e2e.py`.
5. `bun run gen:api`; web shell (layout, header, footer, role switcher, theme, base components).
6. `/report` (M1, M5/M6 frontend) → `/hospital` (M3) → `/transport` (M4) → `/demo` (M8) → `/case` + landing (M10).
7. Engine inspector, forecast UI, polish states, mobile pass.
8. Prod compose + Caddy + deploy script; docs (README, FEATURES, KNOWN_ISSUES, PITCH, DEV_POST).

---

## 17. Post-one-shot workflow (for the team)

After the one-shot lands:

1. **Triage in the first 30 min together.** Run every scenario. Log every problem in `docs/FEEDBACK.md` using the template below. Tag with the F-ID and lane.
2. **Each person takes their lane (§5.2)** and works on their own branch: `lane-a/<F-ID>-short-name`. Small PRs, merge to `main` often.
3. **Contract changes** (`models.py`, API shapes) → announce in chat, change Pydantic, run `bun run gen:api`, commit both in one PR.
4. Keep `docs/FEATURES.md` statuses up to date — it's the shared progress board.

`docs/FEEDBACK.md` template:

```markdown
## FB-001 — <short title>
- **Type:** bug | design | enhancement | cut
- **Feature:** F-M3.3
- **Lane / owner:** C / <name>
- **Severity for demo:** blocker | high | nice-to-have
- **Observed:** what happened (scenario, page, viewport)
- **Expected:** what should happen
- **Notes / fix idea:**
- **Status:** open | in progress | done (commit/PR link)
```

---

## 18. Safety, ethics & honesty (also pitch material)

- Decision **support**, not decision making: every recommendation requires a human (clinician/specialist/coordinator) to act. Presage's FDA clearance itself states it is not intended to independently direct therapy — mirror that language.
- First-aid content comes only from a vetted static library; the LLM selects, never authors, medical instructions.
- All clinical windows, transport speeds, capabilities and baseline durations are **labelled demo assumptions** in the UI and docs.
- No real patient data. Scan videos auto-expire. No PII in URLs (case IDs are UUIDs; short codes are random).
- Never claim Dhivehi voice support unless verified.

## 19. Out of scope (explicitly)

Real authentication, SMS/WhatsApp gateway, integration with national health records or insurance systems, real asset GPS, multi-tenant hospitals, billing, Solana, Snowflake. (Mention SMS/WhatsApp + national system integration as "next steps" in the pitch.)
