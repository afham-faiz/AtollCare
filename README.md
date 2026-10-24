# AtollCare — the patient's story arrives before the patient does

Remote emergency transfers (island, rural, maritime, mountain) can mean 30 minutes to several hours in a boat,
ambulance or aircraft before the patient reaches the hospital that can treat them. Usually the receiving team learns
almost nothing until the doors open.

AtollCare is two connected screens:

- **Crew** (`/crew`): a tablet or laptop on a mount in the vehicle. **Presage** reads heart rate, breathing rate and HRV
  from the camera, hands-free. The crew speak their notes (ElevenLabs Scribe), and the notes become a structured
  handoff. One tap sends it.
- **Hospital** (`/hospital`): who's arriving, how sick they are, what's been given, measurements with their source,
  an SBAR briefing, the ETA, and one primary decision: **Accept**. Questions typed here are spoken aloud in the
  vehicle. The acceptance, and what's being prepared, shows up on the crew screen.

Region-neutral: regions are JSON data packs. The Maldives and the Scottish Western Isles ship as examples.
Product brief: [`docs/BRIEF.md`](docs/BRIEF.md). Decision support only. Every clinical number in the demo is
illustrative.

## Architecture

```
vehicle laptop / tablet                             Vultr VM (Docker Compose, Caddy HTTPS)
┌──────────────────────────────┐                    ┌────────────────────────────────────────────┐
│ browser: crew screen         │── /api (HTTPS) ───►│ engine  FastAPI · NEWS2 · alerts · SBAR     │
│   camera frames (RGBA, WS)   │                    │         sim clock · region packs            │
│        ▼              ▲      │                    │         adapters: gemini · elevenlabs · s3  │
│ presage-bridge  HR/RR/HRV    │── stable vitals ──►│ db      TimescaleDB / Tiger Cloud           │
│ (@smartspectra/node-sdk)     │   every 5 s        │         (in-memory when DATABASE_URL empty) │
└──────────────────────────────┘                    │ web     Next.js 16                          │
         video never leaves the vehicle             └────────────────────────────────────────────┘
hospital browser ── /hospital ── polls /api every 2 s (SWR)
```

- The **engine owns the data and the clinical logic**. Next.js only calls `/api/*`, so keys stay server-side.
- **One source of truth for types:** Pydantic models in `engine/app/models.py` → OpenAPI → `web/src/lib/api-types.ts`
  (`bun run gen:api`).
- **Transfer lifecycle:** `preparing` (crew only) → `pending` (handoff sent; the hospital sees it) → `accepted` →
  `arrived` → `closed`.
- **Honest provenance:** every vital carries its source (`presage`, `manual` or `simulated`) and a timestamp. Simulated
  values are labelled *Simulated* on both screens and "(simulated)" in the SBAR, and get no clinical status word.
- **Only measured values score.** NEWS2, alerts and the deterioration forecast use Presage and crew readings only;
  simulated readings are display-only. Prepared demo cases pre-fill nothing: the presenter types the suggested vitals.
- **Extraction is a suggestion.** Items pulled from a voice note ("Aspirin 300 mg") can be struck by the crew.

## Run locally (no Docker)

```bash
cd engine && uv sync && uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd web && bun install && bun run dev
```

Open http://localhost:3000. It lands on the crew screen. With no keys, everything runs on mock adapters, the
in-memory store and clearly labelled simulated HR / RR.

**Live Presage vitals.** Run the bridge on the machine with the camera (Node 20+):

```bash
cd presage-bridge && npm install && PRESAGE_API_KEY=... ENGINE_URL=http://localhost:8000 npm start
```

Then open the crew screen in Chrome or Edge and allow the camera. Camera and microphone need a secure context
(`localhost` or HTTPS). Embedded preview panes, such as an editor's built-in browser, usually block capture. Details:
[`presage-bridge/README.md`](presage-bridge/README.md).

### With Tiger Data locally (TimescaleDB in Docker)

```bash
docker run -d --name atollcare-tsdb -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=atollcare -p 5433:5432 timescale/timescaledb:latest-pg17
```

Then set `DATABASE_URL=postgresql://postgres:postgres@localhost:5433/atollcare` (or a Tiger Cloud URL) and start the
engine. Or run everything in containers: `cp .env.example .env && docker compose up`.

### Checks

```bash
cd engine && uv run pytest && uv run ruff check app tests ../scripts
```

```bash
cd engine && TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/atollcare_test uv run pytest
```

```bash
cd web && bun run test && bun run typecheck && bun run lint && bun run build
```

```bash
uv run --project engine python scripts/demo_e2e.py --base http://localhost:8000
```

The e2e script plays the story through the API: create → Presage + crew vitals → voice note → handoff (asserting the
hospital can't see the transfer before it) → question and answer → accept → fast-forward to arrival → close.

## Demo

Press **Ctrl + .** (⌘ + . on a Mac) anywhere, or use the sliders icon in the top bar, to open the presenter panel:
prepared cases (each with a line to say and the vitals to type), region, journey speed (1× / 10× / 30× / 60×), service
status (including which database and host are live), network insights with *Seed 60 days of history*, and reset. The
same tools live at `/demo`. The 3-minute script is in [`docs/PITCH.md`](docs/PITCH.md).

**Network insights** (`/insights`, for operations leads, not a clinical screen): handoffs, median and 90th-percentile
time to acceptance, journey times, alerts and hospital questions per day, slowest-accepting hospitals. Answered from
Tiger Data continuous aggregates, with the storage, compression and a live aggregate-vs-raw benchmark beside them.

## Environment

See [`.env.example`](.env.example). Each adapter has a `mock` mode, and a missing key falls back to mock with a log line.

| Variable | Read by | Meaning |
|---|---|---|
| `DATABASE_URL` | engine | Postgres / TimescaleDB / Tiger Cloud. Empty → in-memory store |
| `GEMINI_MODE`, `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL` | engine | `real` → Gemini writes the SBAR and extracts interventions (fallback model when the primary is overloaded); otherwise template + rules |
| `ELEVENLABS_MODE`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_CREW`, `ELEVENLABS_VOICE_HOSPITAL` | engine | `real` → Scribe transcribes voice notes; hospital messages are spoken with ElevenLabs TTS. Otherwise the browser's own speech recognition and synthesis |
| `STORAGE_MODE` (`local`/`s3`), `S3_*` | engine | Where TTS audio is cached |
| `DEFAULT_REGION`, `DEFAULT_SPEED_MULTIPLIER` | engine | Demo defaults |
| `HOST_LABEL`, `HOST_REGION` | engine | Only if Vultr's metadata service isn't reachable from the container |
| `NEXT_PUBLIC_ENGINE_URL`, `ENGINE_INTERNAL_URL` | web | API base for the browser / for the Next.js proxy |
| `NEXT_PUBLIC_PRESAGE_BRIDGE_URL` | web | Default `ws://localhost:8787/ws` |
| `PRESAGE_API_KEY`, `ENGINE_URL`, `PORT` | presage-bridge | `node --env-file=../.env src/index.js`, or set in its shell |

## Tiger Data

Put a Tiger Cloud service URL in `DATABASE_URL` (keep `?sslmode=require`) and start the engine. Migrations in
`engine/app/migrations/` run idempotently:

| Object | What it does |
|---|---|
| `vitals_readings`, `transfer_notes` | Hypertables with one-day chunks: every reading and every timeline entry |
| `vitals_1m` | Continuous aggregate (real-time) of **measured** readings → the hospital's trend chart and the deterioration forecast. The chart shows which aggregate answered and how many ms it took |
| `network_vitals_1h`, `network_events_1d` | Continuous aggregates behind Network insights (reading volume, alerts, questions) |
| Compression | Columnar compression after 7 days, segmented by transfer: 71 MB → 12 MB (83%) on 60 days of seeded history |
| `transfers` | Relational document per transfer in the same database (outcomes, time to acceptance via `percentile_cont`) |

Measured on a laptop with 60 days of seeded history (351k readings): every insights query 1–5 ms; readings per hour
over 30 days from `network_vitals_1h` in 2.6 ms vs 22.8 ms scanning 189k raw rows (8.8×). Seeding takes 10–20 s.

## Deploy to Vultr

Step-by-step runbook: [`docs/DEPLOY_VULTR.md`](docs/DEPLOY_VULTR.md). In short: a 2 vCPU / 4 GB Ubuntu instance, ports
80/443 open, real keys in `.env`, then `VULTR_HOST=<ip> ./scripts/deploy_vultr.sh`. Caddy gets a certificate for
`<ip>.sslip.io` automatically; the engine reads Vultr's instance metadata and the presenter panel shows the region it
is running in. Both production images are built and smoke-tested (web → engine → TimescaleDB). The bridge stays in the
vehicle and points its `ENGINE_URL` at the public HTTPS URL.

## Sponsor tracks

| Track | Role | Where |
|---|---|---|
| **Presage** (main) | Live HR, RR, HRV, breathing waveform and framing hints from a mounted camera | `presage-bridge/`, `web/src/lib/presage.ts`, `crew/[transferId]/CameraInstrument.tsx` |
| ElevenLabs | Crew voice notes → text (Scribe); hospital questions and alerts spoken in the vehicle | `engine/app/adapters/elevenlabs.py`, `web/src/lib/{dictation,speech}.ts` |
| Gemini | Live SBAR from vitals + notes; interventions extracted from speech | `engine/app/adapters/gemini.py`, `engine/app/core/briefing.py` |
| Tiger Data | Hypertables, measured-only `vitals_1m` → trend + forecast, network aggregates, columnar compression, Network insights with a live benchmark | `engine/app/migrations/`, `engine/app/db.py`, `web/src/app/(main)/insights/` |
| Vultr | Compute + Caddy HTTPS, region shown from instance metadata, optional Object Storage | `docker-compose.prod.yml`, `Caddyfile`, `scripts/deploy_vultr.sh`, `docs/DEPLOY_VULTR.md` |

## Docs

[`docs/BRIEF.md`](docs/BRIEF.md) product brief · [`docs/DEPLOY_VULTR.md`](docs/DEPLOY_VULTR.md) deploy runbook ·
[`docs/FEATURES.md`](docs/FEATURES.md) what's built and how it was
verified · [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) what isn't verified · [`docs/PITCH.md`](docs/PITCH.md) demo
script · [`docs/DEV_POST.md`](docs/DEV_POST.md) write-up draft · [`docs/CONCEPT.md`](docs/CONCEPT.md) and
[`docs/PRD.md`](docs/PRD.md) the original v1 concept and PRD (historical).
