# AtollCare — island-to-specialist emergency coordination

A shared, live **Case** that travels with the patient: contactless vitals and AI-structured intake on the island, a
clinically grounded **decision engine** that picks the fastest route to the *right* hospital within the condition's
treatment window, one-click specialist acceptance in Malé, and live transport tracking — every handoff in **parallel**
instead of a sequential phone chain.

> **Symptom → definitive care: X h Y min. Estimated Z min faster than the phone-chain baseline.**

Built for OxHack '26 from [`docs/PRD.md`](docs/PRD.md). The team's original concept note is in
[`docs/CONCEPT.md`](docs/CONCEPT.md). Decision support only — every recommendation needs a clinician to act. All
clinical windows, transport speeds, capabilities and baseline durations are **DEMO ASSUMPTIONS**.

## Architecture

```
┌──────────────────────────── Vultr VM (Docker Compose) ───────────────────────────┐
│  Caddy (HTTPS)  ├── /       → web    (Next.js 16, bun)  :3000                    │
│                 └── /api/*  → engine (FastAPI, uv)      :8000                    │
│  engine: adapters/ (presage · gemini · elevenlabs · storage — each real | mock)  │
│          core/ (news2 · conditions · routing · decision · forecast · baseline)   │
│          sim/  transport simulator on an accelerated sim clock                   │
│          db ──► Tiger Cloud / TimescaleDB  (local: timescale container,          │
│                 or in-memory store when DATABASE_URL is empty)                   │
│  object storage ──► Vultr Object Storage (S3)  (local: ./var/storage)            │
└──────────────────────────────────────────────────────────────────────────────────┘
Frontend realtime = SWR polling every 2 s.
```

- The **engine owns the database and all business logic**; Next.js only calls `/api/*`. Keys stay server-side.
- **Single source of truth for types:** Pydantic models in `engine/app/models.py` → OpenAPI → `web/src/lib/api-types.ts`
  (`bun run gen:api`).
- **Simulated clock** (`engine/app/core/clock.py`): offset + speed multiplier, so the night scenario works at a daytime
  pitch.

## Run locally

### Option A — Docker (TimescaleDB, matches production)

```bash
cp .env.example .env
docker compose up
```

Web: http://localhost:3000 · Engine: http://localhost:8000/docs. Works with no API keys (all adapters `mock`).

### Option B — no Docker (in-memory store)

```bash
cd engine
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd web
bun install
bun run dev
```

Leaving `DATABASE_URL` empty runs the engine on an in-process store (same interface as Postgres). Data resets when the
engine restarts. Point `DATABASE_URL` at any TimescaleDB / Tiger Cloud / Postgres to persist.

### Checks

```bash
cd engine && uv run pytest
```

```bash
cd web && bun run typecheck && bun run lint && bun run build
```

```bash
uv run --project engine python scripts/demo_e2e.py --base http://localhost:8000
```

The e2e script plays the hero scenario through the API (create → intake → vitals → assess → refer → accept → dispatch
→ simulate to arrival at 300× → close) and asserts `closed` with `saved_vs_baseline_min > 0`.

### Regenerating API types

```bash
cd web && bun run gen:api
```

## Demo

Open **/demo**, tick *Autoplay*, load **Night-time heart attack, Laamu** (hero). Then show:

| Page | What it shows |
|---|---|
| `/report/[caseId]` | Mobile-first island view: case code, intake chips, camera scan / manual vitals, NEWS2, route + *why*, first-aid voice |
| `/hospital` · `/hospital/[caseId]` | Inbox, SBAR, vitals trend + forecast (Tiger Data), accept / decline / request info, capacity, time saved, engine inspector |
| `/transport` · `/transport/[caseId]` | Weather & daylight banner, dispatch board, live map, asset roster, crew brief |
| `/case/[caseId]` | Read-only family link with QR code |
| `/demo?view=split` | Presenter view: phone frame + hospital + map |

World controls in `/demo`: Day 14:00 / Night 21:00, speed 1×–300×, sea state, wind, visibility, helicopter toggle.
The 3-minute script is in [`docs/PITCH.md`](docs/PITCH.md).

## Environment variables

See [`.env.example`](.env.example). Every adapter has a `mock` mode; a missing key falls back to mock with a log line.

| Variable | Meaning |
|---|---|
| `DATABASE_URL` | Postgres / TimescaleDB / Tiger Cloud URL. Empty → in-memory store |
| `GEMINI_MODE`, `GEMINI_API_KEY`, `GEMINI_MODEL` | `real` enables structured intake, SBAR, route explanation, guidance ordering |
| `ELEVENLABS_MODE`, `ELEVENLABS_API_KEY`, `ELEVENLABS_*` | `real` enables Scribe STT and TTS (MP3 cached in object storage) |
| `PRESAGE_MODE` (`sdk`/`cloud`/`mock`/`manual`), `PRESAGE_*` | Contactless HR/RR from a face video — real paths marked `TODO(presage-verify)` |
| `STORAGE_MODE` (`local`/`s3`), `S3_*` | Vultr Object Storage for scan videos and TTS audio |
| `PUBLIC_HOST` | Caddy host — your domain or `<ip>.sslip.io` |
| `DEFAULT_SPEED_MULTIPLIER`, `TIMEZONE` | Sim clock defaults |
| `NEXT_PUBLIC_MAP_TILES` | Optional tile URL template (default OpenStreetMap) |

## Tiger Cloud (Tiger Data)

1. Create a service at console.cloud.timescale.com (TimescaleDB enabled by default).
2. Copy the connection string into `DATABASE_URL` (keep `?sslmode=require`).
3. Start the engine — migrations in `engine/app/migrations/` run idempotently (tracked in `schema_migrations`), creating
   hypertables for `vitals_readings`, `transport_positions`, `case_events` and the `vitals_1m` continuous aggregate
   (real-time aggregation on). `/demo` reset deletes rows only; migrations never drop tables.

## Deploy to Vultr

1. Create an **Ubuntu Cloud Compute** instance; open ports **80** and **443** in the firewall group.
2. Optional: create **Vultr Object Storage**, a bucket, and add a lifecycle rule expiring `scans/` after 24 h. Set
   `STORAGE_MODE=s3`, `S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY`, `S3_SECRET_KEY`.
3. Put real keys in `.env` and set `PUBLIC_HOST=<ip>.sslip.io` (instant HTTPS) or your domain.
4. Deploy:

```bash
VULTR_HOST=<ip> ./scripts/deploy_vultr.sh
```

The script installs Docker if needed, syncs the repo, and runs `docker compose -f docker-compose.prod.yml up -d --build`.
Camera and microphone need HTTPS, which Caddy provides.

## Hackathon tracks

| Track | What we use | Where |
|---|---|---|
| Presage | 30 s face scan → HR + RR → NEWS2 + trend | `engine/app/adapters/presage.py`, `web/src/app/components/(vitals)/CameraScan.tsx` |
| Gemini | Structured intake, SBAR, route explanation, vetted-guidance selection | `engine/app/adapters/gemini.py` |
| ElevenLabs | Scribe voice intake, spoken first aid, status updates, crew brief | `engine/app/adapters/elevenlabs.py`, `components/(voice)` |
| Tiger Data | Hypertables + `vitals_1m` continuous aggregate → trend chart + forecast | `engine/app/migrations/001_init.sql`, `engine/app/db.py` |
| Vultr | Compute + Caddy HTTPS + Object Storage | `docker-compose.prod.yml`, `Caddyfile`, `scripts/deploy_vultr.sh` |
| DEV | Project write-up | `docs/DEV_POST.md` |

## Docs

- [`docs/FEATURES.md`](docs/FEATURES.md) — every feature ID with status and files
- [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) — what is unverified or rough
- [`docs/FEEDBACK.md`](docs/FEEDBACK.md) — post-one-shot triage log
- [`docs/PITCH.md`](docs/PITCH.md) · [`docs/DEV_POST.md`](docs/DEV_POST.md)

## Repo layout & lanes

`engine/app/{core,adapters,data}` → Lane A · `web/src/app/(main)/report`, `components/(vitals|voice)` → Lane B ·
`web/src/app/(main)/{hospital,transport,demo}`, `components/(map)`, `engine/app/sim` → Lane C · `models.py`,
`components/(case)`, platform → shared (heads-up in chat before changing). Every file starts with its feature ID.
