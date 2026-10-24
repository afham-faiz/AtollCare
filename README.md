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
  values are labelled *Demo signal* on both screens and "(demo signal)" in the SBAR.

## Run locally (no Docker)

```bash
cd engine && uv sync && uv run uvicorn app.main:app --reload --port 8000
```

```bash
cd web && bun install && bun run dev
```

Open http://localhost:3000. It lands on the crew screen. With no keys, everything runs on mock adapters, the
in-memory store and a labelled demo signal for HR / RR.

**Live Presage vitals.** Run the bridge on the machine with the camera (Node 20+):

```bash
cd presage-bridge && npm install && PRESAGE_API_KEY=... ENGINE_URL=http://localhost:8000 npm start
```

Then open the crew screen in Chrome or Edge and allow the camera. Camera and microphone need a secure context
(`localhost` or HTTPS). Embedded preview panes, such as an editor's built-in browser, usually block capture. Details:
[`presage-bridge/README.md`](presage-bridge/README.md).

### Docker (TimescaleDB, as in production)

```bash
cp .env.example .env && docker compose up
```

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

The e2e script plays the story through the API: create → Presage + crew vitals → voice note → handoff (asserting the
hospital can't see the transfer before it) → question and answer → accept → fast-forward to arrival → close.

## Demo

Press **Ctrl + .** (⌘ + . on a Mac) anywhere, or use the sliders icon in the top bar, to open the presenter panel:
prepared cases (each with a line to say), region, journey speed (1× / 10× / 30× / 60×), service status, reset. The
same tools live at `/demo`. The 3-minute script is in [`docs/PITCH.md`](docs/PITCH.md).

## Environment

See [`.env.example`](.env.example). Each adapter has a `mock` mode, and a missing key falls back to mock with a log line.

| Variable | Read by | Meaning |
|---|---|---|
| `DATABASE_URL` | engine | Postgres / TimescaleDB / Tiger Cloud. Empty → in-memory store |
| `GEMINI_MODE`, `GEMINI_API_KEY`, `GEMINI_MODEL` | engine | `real` → Gemini writes the SBAR and extracts interventions; otherwise template + rules |
| `ELEVENLABS_MODE`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_CREW`, `ELEVENLABS_VOICE_HOSPITAL` | engine | `real` → Scribe transcribes voice notes; hospital messages are spoken with ElevenLabs TTS. Otherwise the browser's own speech recognition and synthesis |
| `STORAGE_MODE` (`local`/`s3`), `S3_*` | engine | Where TTS audio is cached |
| `DEFAULT_REGION`, `DEFAULT_SPEED_MULTIPLIER` | engine | Demo defaults |
| `NEXT_PUBLIC_ENGINE_URL`, `ENGINE_INTERNAL_URL` | web | API base for the browser / for the Next.js proxy |
| `NEXT_PUBLIC_PRESAGE_BRIDGE_URL` | web | Default `ws://localhost:8787/ws` |
| `PRESAGE_API_KEY`, `ENGINE_URL`, `PORT` | presage-bridge | Set in the bridge's own shell; it does not read `.env` |

## Tiger Cloud (Tiger Data)

Put the service URL in `DATABASE_URL` (keep `?sslmode=require`) and start the engine. `engine/app/migrations/`
runs idempotently and creates hypertables `vitals_readings` and `transfer_notes`, plus the `vitals_1m` continuous
aggregate (real-time aggregation on) that feeds the trend chart and the deterioration forecast.

## Deploy to Vultr

1. Ubuntu Cloud Compute instance; open ports 80 and 443.
2. Real keys in `.env`; `PUBLIC_HOST=<ip>.sslip.io` (instant HTTPS) or your domain.
3. `VULTR_HOST=<ip> ./scripts/deploy_vultr.sh` installs Docker if needed, syncs the repo, and runs
   `docker compose -f docker-compose.prod.yml up -d --build`.

The bridge stays in the vehicle. Point its `ENGINE_URL` at the public HTTPS URL.

## Sponsor tracks

| Track | Role | Where |
|---|---|---|
| **Presage** (main) | Live HR, RR, HRV, breathing waveform and framing hints from a mounted camera | `presage-bridge/`, `web/src/lib/presage.ts`, `crew/[transferId]/CameraInstrument.tsx` |
| ElevenLabs | Crew voice notes → text (Scribe); hospital questions and alerts spoken in the vehicle | `engine/app/adapters/elevenlabs.py`, `web/src/lib/{dictation,speech}.ts` |
| Gemini | Live SBAR from vitals + notes; interventions extracted from speech | `engine/app/adapters/gemini.py`, `engine/app/core/briefing.py` |
| Tiger Data | Vitals hypertable + 1-minute continuous aggregate → trend + forecast | `engine/app/migrations/001_init.sql`, `engine/app/db.py` |
| Vultr | Compute + Caddy HTTPS + Object Storage | `docker-compose.prod.yml`, `Caddyfile`, `scripts/deploy_vultr.sh` |

## Docs

[`docs/BRIEF.md`](docs/BRIEF.md) product brief · [`docs/FEATURES.md`](docs/FEATURES.md) what's built and how it was
verified · [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) what isn't verified · [`docs/PITCH.md`](docs/PITCH.md) demo
script · [`docs/DEV_POST.md`](docs/DEV_POST.md) write-up draft · [`docs/CONCEPT.md`](docs/CONCEPT.md) and
[`docs/PRD.md`](docs/PRD.md) the original v1 concept and PRD (historical).
