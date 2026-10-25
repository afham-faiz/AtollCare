# AtollCare — the patient's story arrives before the patient does

Remote emergency transfers (island, rural, maritime, mountain) can mean 30 minutes to several hours in a boat,
ambulance or aircraft before the patient reaches the hospital that can treat them. Usually the receiving team learns
almost nothing until the doors open.

AtollCare turns the phone everyone already has into the first monitor in the chain, and carries one patient story
through three connected screens. What is captured once is never asked again. Decision support only; every clinical
number in the demo is illustrative.

## What it does

| Screen | Who, on what | What happens |
|---|---|---|
| **Pre-arrival** `/pre-arrival` | The companion, on their own phone, before anyone reaches the health centre | "Call 102 first", consent, then film the patient for 30–60 seconds while saying what happened. **Presage** reads heart and breathing rate from the camera, live, with hints on how to frame the shot. The spoken words become the account. **Gemini** checks still frames for visible signs and cites the frame it saw each one in. Optional ID photo, read by Gemini. Nothing reaches the health centre until they press **Send**. |
| **Crew** `/crew` | The ambulance or boat crew, on a phone or a mounted tablet or laptop | A sent packet appears under "Sent ahead from a phone"; one tap starts the transfer from it, account, ID and video carried over. Contactless **scans** on a propped-up phone, as often as the patient's acuity calls for (or a continuous stream from a mount). Oximeter, BP, temperature and consciousness are entered by hand. Spoken notes become a structured handoff (SBAR). Hospital replies are read aloud. |
| **Hospital** `/hospital` | The receiving team, on a desktop or tablet | A tile with the latest Presage heart and breathing rate, the trace, how long before arrival they knew, the camera trend and the oximeter cross-check. Every measurement with its source and age, what was seen on video (with the frame), the companion's account and ID, the SBAR, and one primary decision: **Accept**. They can also ask the crew a question. |
| **Network insights** `/insights` | Operations leads | Handoffs, median and 90th-percentile time to acceptance, journey times, alerts and questions per day, slowest-accepting hospitals. Needs a database to show anything (see below). |

Also in the app: a **presenter panel** (press **Ctrl + .**, or ⌘ + . on a Mac) with prepared demo cases, region
choice, journey speed (1× to 60×), service status, and a **QR code that opens a screen on a phone**. The same tools are
at `/demo`.

**Rules the app holds itself to**

- **Honest provenance.** Every vital carries its source (`presage`, `manual` or `simulated`) and a timestamp.
  Simulated values are labelled and never scored.
- **Presage's verdict decides.** A reading Presage calls stable (±3 bpm, ±1 breath/min) is scored; anything else is
  shown and labelled. A camera reading alone never raises a critical alert and counts for 15 minutes. The companion's
  reading is a bystander estimate and is never scored.
- **Only measured values score.** NEWS2, alerts and the deterioration forecast use Presage and crew readings only.
- **Extraction is a suggestion.** Items pulled from a voice note ("Aspirin 300 mg") can be struck by the crew.
- **Privacy.** Clips are analysed in memory and not stored; only the frames a finding cites are kept.
- **Region-neutral.** Regions are JSON packs in `engine/app/data/regions/`. The Maldives and the Scottish Western
  Isles ship as examples.

## How it fits together

```
phone (companion / crew) ──► web  Next.js · the three screens · proxies /api and /presage
                              │
                              ├─ /api ────────► engine  FastAPI · NEWS2 · alerts · forecast · SBAR · intake services
                              │                          (sign check, ID read, speech) · Gemini · ElevenLabs
                              └─ /presage/ws ─► presage-bridge  Node · Presage SmartSpectra SDK
                                                  live JPEG frames in, heart / breathing rate and waveforms out
```

- **`engine/`** owns the data and the clinical logic. The browser only ever calls `/api/*` through the web app, so
  keys stay on the server. With no database it keeps everything in memory (it resets on restart), which is the normal
  way to run it.
- **`web/`** is Next.js 16 / React 19. It proxies `/api` to the engine and `/presage` (HTTP and WebSocket) to the
  bridge, so **one address** serves the app, the API and Presage. That matters for phones, which only allow their
  camera on HTTPS.
- **`presage-bridge/`** runs the official Presage SmartSpectra Node SDK. A phone streams frames to it live; if the
  phone cannot stream, the engine sends the uploaded clip to it instead. Details in
  [`presage-bridge/README.md`](presage-bridge/README.md).
- **Types** have one source: Pydantic models in `engine/app/models.py` → OpenAPI → `web/src/lib/api-types.ts`.
- **Lifecycles.** Packet: `draft` → `sent` → `started`. Transfer: `preparing` → `pending` (the hospital can now see
  it) → `accepted` → `arrived` → `closed`.

## Quickstart (Windows, macOS or Linux; no Docker)

You need **Python 3.11+**, **Node 20+** and a terminal for each of three services. The commands below are for
PowerShell on Windows; on macOS/Linux use `source .venv/bin/activate` and forward slashes.

**Windows shortcut.** Do steps 1 and 2's `python -m venv` and `pip install` once, then from the repo folder in
PowerShell:

```powershell
.\scripts\start.ps1
```

It installs the web and bridge npm packages on first run, starts the engine, the Presage bridge, the web app and the
Cloudflare tunnel (each in its own window), waits until they answer, and opens the phone-ready
`https://…trycloudflare.com` address. Options: `-NoTunnel` for local only (http://localhost:3000), `-Prod` for a
production web build, `-Stop` to close everything. If PowerShell says running scripts is disabled, use
`powershell -ExecutionPolicy Bypass -File .\scripts\start.ps1`. The rest of this section is the same thing by hand.

### 1. Configure

Create a file named `.env` in the **repo root** (git-ignored). Both the engine and the bridge look there. Section 2
lists every setting; the smallest useful file is:

```ini
GEMINI_MODE=real
GEMINI_API_KEY=your-google-key
GEMINI_USE_ENTERPRISE=false        # true only for a Google Cloud / Agent Platform (Vertex) key
PRESAGE_API_KEY=your-presage-key   # https://physiology.presagetech.com
```

With none of these, everything still runs on mock adapters with clearly labelled simulated heart and breathing rate,
which is enough to click through the whole flow.

> Do not copy [`.env.example`](.env.example) as it stands: it still points `DATABASE_URL` at a Docker database that
> no longer exists in our setup, and the engine would fail to connect. Leave `DATABASE_URL` empty.

### 2. Start the three services

**Engine** (port 8000):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install fastapi "uvicorn[standard]" pydantic pydantic-settings asyncpg pyyaml httpx python-multipart google-genai boto3 tzdata imageio-ffmpeg==0.6.0
cd engine
uvicorn app.main:app --reload --port 8000
```

If you have [uv](https://docs.astral.sh/uv/), `cd engine && uv sync && uv run uvicorn app.main:app --reload --port 8000`
does the same from the lockfile. ffmpeg comes bundled with `imageio-ffmpeg`.

**Presage bridge** (port 8787), only needed for real heart and breathing rate:

```powershell
cd presage-bridge
npm install
node --env-file=../.env src/index.js
```

**Web app** (port 3000):

```powershell
cd web
npm install
npm run dev
```

(`bun install && bun run dev` works too; the lockfile is bun's.)

### 3. Open it

Go to **http://localhost:3000**. It lands on the crew screen; the companion's screen is `/pre-arrival` and the
hospital's is `/hospital`. Press **Ctrl + .** for the presenter panel, pick a prepared case, and play the story.

Camera and microphone need a secure context: `localhost` works in Chrome or Edge, but an editor's built-in preview
pane usually blocks capture.

### 4. Use it on a phone

A phone only gets its camera on HTTPS, so the web app has to be reachable at an `https://` address.

```powershell
winget install --id Cloudflare.cloudflared    # once
bash scripts/phone_tunnel.sh                  # Git Bash or WSL; prints https://<random>.trycloudflare.com
```

Open the printed address on the laptop, press **Ctrl + .**, and scan the **On a phone** QR code. The address is
public while the tunnel runs; stop it with Ctrl + C when you are done. For anything on stage, use a production build
(`npm run build && npm run start` in `web/`), which loads much faster on a phone than the dev server.

Before a demo, `node scripts/predemo_check.mjs` checks the whole chain through that address, Presage and Gemini
included (`--quick` checks only the services).

## Settings (`.env` in the repo root)

Every setting has a default or a mock fallback, so nothing is strictly required. A missing key falls back to mock mode
with a log line. Restart the service after editing.

**Keys and mode**

| Variable | Used by | Meaning |
|---|---|---|
| `GEMINI_MODE` | engine | `real` turns Gemini on everywhere (SBAR, note extraction, sign check, ID read, speech). Anything else uses templates and rules. Default `mock` |
| `GEMINI_API_KEY` | engine | Your Google key. Read only when `GEMINI_MODE=real` |
| `GEMINI_USE_ENTERPRISE` | engine | `true` for a Google Cloud / Agent Platform (Vertex) key, whose API restrictions must allow the Vertex AI API (otherwise `API_KEY_SERVICE_BLOCKED`); `false` for an AI Studio key (starts with `AIza`). Default `false` |
| `PRESAGE_API_KEY` | presage-bridge | Required for real measurement. Without it the bridge runs and reports `no_api_key`; scans still run Gemini's sign check and say plainly that heart and breathing rate were not measured |
| `ELEVENLABS_MODE`, `ELEVENLABS_API_KEY` | engine | `real` uses ElevenLabs Scribe for speech to text and speaks hospital messages aloud. Otherwise the browser's own speech recognition and synthesis. Optional: `ELEVENLABS_VOICE_CREW`, `ELEVENLABS_VOICE_HOSPITAL`, `ELEVENLABS_TTS_MODEL`, `ELEVENLABS_STT_MODEL` |

**Gemini models** (engine; the defaults are in `engine/app/config.py` and `engine/app/intake/config.py`)

| Variable | Meaning |
|---|---|
| `GEMINI_MODEL`, `GEMINI_FALLBACK_MODEL` | SBAR writing and note extraction; the fallback is tried once if the first is overloaded |
| `GEMINI_VQA_MODEL` | Sign check on video frames |
| `GEMINI_STT_MODEL`, `GEMINI_STT_FALLBACK_MODEL` | Speech to text through Gemini (a `flash` model sends text after each pause; a `live` model streams, but Google refuses those for express-mode keys) |
| `GEMINI_ID_MODEL`, `GEMINI_CUE_PLANNER_MODEL`, `GEMINI_CHAT_MODEL` | ID photo read, which signs to look for, chat |
| `VQA_MODE` | `one_pass` (default) or `two_step` |
| `VQA_FRAME_INTERVAL_S`, `VQA_MAX_FRAMES` | Frame sampling for the sign check (default every 2 s, at most 24) |
| `GEMINI_VQA_THINKING` | `minimal`, `low` (default, about 20 s per clip), `medium`, `high` or `default` |
| `GEMINI_TIMEOUT_S`, `GEMINI_RETRY_ATTEMPTS` | Give up and retry settings for intake requests |
| `TRANSCRIBE_LANGUAGE`, `STT_SILENCE_STOP_S`, `STT_FLASH_PAUSE_S`, `STT_FLASH_MAX_SEGMENT_S`, `VIDEO_RECORD_MAX_S`, `SAVE_RECORDINGS` | Speech and recording behaviour. `SAVE_RECORDINGS` is `false` by default; recordings are patient data and git-ignored |

**Wiring and demo**

| Variable | Used by | Meaning |
|---|---|---|
| `PRESAGE_BRIDGE_URL` | engine | Where clips are measured when a phone could not stream. Default `http://127.0.0.1:8787` |
| `ENGINE_URL`, `PORT` | presage-bridge | The engine it reports to (default `http://localhost:8000`) and its own port (default `8787`) |
| `ENGINE_INTERNAL_URL` | web | Where Next proxies `/api` (default `http://localhost:8000`) |
| `PRESAGE_BRIDGE_INTERNAL_URL` | web | Where Next proxies `/presage` (default `http://127.0.0.1:8787`) |
| `NEXT_PUBLIC_ENGINE_URL`, `NEXT_PUBLIC_PRESAGE_BRIDGE_URL` | web | Browser-side overrides. Normally leave unset: the app uses its own address |
| `DEFAULT_REGION`, `DEFAULT_SPEED_MULTIPLIER` | engine | Demo defaults (`maldives`, `1`) |
| `CORS_ORIGINS` | engine | Default `http://localhost:3000` |
| `DATABASE_URL` | engine | **Leave empty.** Empty means the in-memory store. A Postgres/TimescaleDB URL still works and is the only way to get data on `/insights`, but it is not part of the current setup |
| `STORAGE_MODE`, `S3_*` | engine | `local` (default) keeps cached speech audio and cited frames on disk under `engine/var/`; `s3` is optional |

## Checks

```powershell
cd engine; pytest; ruff check app tests ../scripts
cd web; npm run test; npm run typecheck; npm run lint; npm run build
python scripts/demo_e2e.py --base http://localhost:8000
```

The e2e script plays the story through the API against a running engine: create → vitals → voice note → handoff
(asserting the hospital cannot see it earlier) → question and answer → accept → arrival → close. (`bun run test` is
the web test runner; it needs bun.)

## More

- [`docs/BRIEF.md`](docs/BRIEF.md) product brief · [`docs/FEATURES.md`](docs/FEATURES.md) what is built and how it
  was verified · [`docs/KNOWN_ISSUES.md`](docs/KNOWN_ISSUES.md) what is not verified · [`docs/PITCH.md`](docs/PITCH.md)
  demo script · [`docs/PART1.md`](docs/PART1.md) how the pre-arrival services are wired in.
- [`presage-bridge/README.md`](presage-bridge/README.md) Presage protocol, and how to get a good measurement
  (phone propped up, face and chest in view, well lit, patient still).
- [`part1/`](part1/) is the standalone Part 1 prototype, kept whole so it still runs on its own (copy `env.example`
  to `inputs/.env`, `pip install -r requirements.txt`, `python run.py --serve`).
- Optional and legacy, not our current path: Docker Compose files (`docker-compose*.yml`), the Vultr deploy
  ([`docs/DEPLOY_VULTR.md`](docs/DEPLOY_VULTR.md), `scripts/deploy_vultr.sh`, `Caddyfile`) and the TimescaleDB /
  Tiger Data migrations in `engine/app/migrations/`. `docs/CONCEPT.md` and `docs/PRD.md` are the original v1 concept.
