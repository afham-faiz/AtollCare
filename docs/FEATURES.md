# Feature checklist (v2: two screens + network insights)

✅ built and exercised · ⚠️ built, not verified end to end (see the note) · ❌ not built.

**How it was verified:** 88 engine tests, run against both the in-memory store and TimescaleDB 2.31 / Postgres 17
(`TEST_DATABASE_URL`); 7 web unit tests (`bun run test`); `scripts/demo_e2e.py` against a live engine; `ruff check`,
`bun run typecheck`, `lint` and `build`; production images built and smoke-tested; browser passes at 1440×900,
1024×768 and 390×844. Real Gemini and ElevenLabs calls verified; camera and mic seen working in Chrome by a teammate.

## Crew screen — `/crew`, `/crew/[transferId]`

| Feature | Status | Files |
|---|---|---|
| Start a transfer: "What's happening" (type or dictate), age, sex, from → to, transport | ✅ | `crew/CrewStartClient.tsx` |
| Monitor hierarchy: patient + status → camera instrument → vitals → note dock → next action; fits 1024×768 | ✅ | `crew/[transferId]/CrewClient.tsx` |
| Camera instrument: face + upper-chest guide, acquiring sweep, framing hints, 30 s breathing settle | ⚠️ live phases need a Presage measurement | `CameraInstrument.tsx`, `lib/presage.ts` |
| Says why it isn't measuring (API key missing / bridge offline / unavailable); blocked / busy / no-camera states; any-size camera fallback | ✅ | `CameraInstrument.tsx`, `lib/presage.ts` |
| Presage live HR / RR / HRV + breathing wave; >110 BPM flagged "confirm with a monitor" | ⚠️ SDK ready with a real key; no live face measurement observed yet | `VitalsPanel.tsx`, `BreathingWave.tsx` |
| Simulated values: labelled, muted, no status word; never scored | ✅ | `VitalsPanel.tsx`, `services/transfers.py` |
| Crew-entered SpO₂ / BP / temp / ACVPU with freshness; "Complete NEWS2" | ✅ | `VitalsSheet.tsx`, `VitalsPanel.tsx` |
| Alerts (NEWS2 band, HR trend, forecast) from measured readings only, with "+N more" | ✅ | `core/alerts.py`, `VitalsPanel.tsx` |
| Voice note: real mic level, live transcript, Scribe or browser speech → structured chips | ✅ | `VoiceCapture.tsx`, `lib/dictation.ts` |
| Strike a wrong extraction (chip ×, or in the handoff's "Given" list); recorded in the timeline | ✅ | `VoiceCapture.tsx`, `SbarDocument.tsx`, `services/transfers.py` |
| Typed notes stored as `text`, dictated as `voice` | ✅ | `VoiceCapture.tsx` |
| Hospital question lands on the mic; answer by voice or typing | ✅ | `VoiceCapture.tsx` |
| Review + send handoff (urgency, sourced vitals, simulated disclaimer, SBAR) | ✅ | `HandoffSheet.tsx` |
| Acceptance + hospital's message in the dock; "Arrived" → "Close transfer" | ✅ | `CrewClient.tsx` |
| Hospital messages and alerts read aloud (ElevenLabs voice, browser fallback) | ✅ | `lib/speech.ts` |

## Hospital screen — `/hospital`, `/hospital/[transferId]`

| Feature | Status | Files |
|---|---|---|
| Incoming rail; only handed-off transfers appear | ✅ | `hospital/HospitalClient.tsx`, `services/transfers.py` |
| Hero: working impression with its source and the crew's words; arrival time; **Accept transfer** | ✅ | `hospital/TransferDetail.tsx` |
| Container-query layout (rail-aware); sticky decision bar on phones | ✅ | `hospital/Hospital.module.scss` |
| Vitals strip with status word, source and freshness; simulated muted | ✅ | `TransferDetail.tsx` |
| Handoff: SBAR (Gemini or template, labelled) + "Given" list | ✅ | `components/(transfer)/SbarDocument.tsx` |
| Trend from `vitals_1m`, with source and query time shown | ✅ | `TrendChart.tsx`, `db.py` |
| Ask the crew; accept with preparation + message | ✅ | `TransferDetail.tsx`, `AcceptModal.tsx` |
| Dead links explain themselves (crew offers "Start a demo case") | ✅ | `CrewClient.tsx`, `TransferDetail.tsx` |

## Network insights — `/insights` (Tiger Data)

| Feature | Status | Files |
|---|---|---|
| KPIs: handoffs, median + p90 time to acceptance, median journey, high-risk count | ✅ | `insights/InsightsClient.tsx`, `services/insights.py` |
| Transfers / alerts / questions per day (small multiples, table view) | ✅ | `InsightsClient.tsx` |
| Slowest-accepting hospitals first | ✅ | `db.py` |
| Storage proof: rows, chunks, compressed chunks, before → after | ✅ | `db.py::insights` |
| Timed queries + live continuous-aggregate-vs-raw benchmark | ✅ | `db.py::benchmark` |
| Seed 60 days of simulated history (server-side `generate_series`), flagged and kept out of clinical screens | ✅ | `db.py::seed_history` |
| Honest "needs Tiger Data" state on the in-memory store | ✅ | `services/insights.py` |

## Engine

| Feature | Status | Files |
|---|---|---|
| Lifecycle `preparing → pending → accepted → arrived → closed` | ✅ | `services/transfers.py` |
| NEWS2, forecast, alerts with hysteresis — measured readings only | ✅ | `core/`, `services/transfers.py` |
| SBAR: Gemini with template fallback; "(simulated)" labelling | ✅ | `core/briefing.py`, `adapters/gemini.py` |
| Gemini fallback model; extraction tries the fast model first under a 5 s deadline | ✅ | `adapters/gemini.py`, `tests/test_gemini.py` |
| Extraction rules: clause-by-clause, spoken units, dose before drug | ✅ | `core/briefing.py` |
| Scribe STT, TTS with storage cache | ✅ local · ⚠️ S3 | `adapters/elevenlabs.py` |
| Prepared cases start empty; suggested vitals for the presenter | ✅ | `services/transfers.py`, `PresenterTools.tsx` |
| TimescaleDB: hypertables, 3 continuous aggregates, compression, one-day chunks | ✅ local TimescaleDB · ⚠️ Tiger Cloud | `migrations/001_init.sql`, `migrations/002_tiger.sql` |
| Infra facts in `/api/meta` (database + version, Vultr region from metadata) | ✅ local · ⚠️ on Vultr | `core/infra.py` |

## Deploy (Vultr)

| Feature | Status | Files |
|---|---|---|
| Production images (engine, web) | ✅ built + smoke-tested | `engine/Dockerfile`, `web/Dockerfile` |
| Compose + Caddy HTTPS (sslip.io) | ⚠️ not yet on a Vultr instance | `docker-compose.prod.yml`, `Caddyfile` |
| Deploy script (git archive over SSH; rsync / git modes) + runbook | ⚠️ not yet run against an instance | `scripts/deploy_vultr.sh`, `docs/DEPLOY_VULTR.md` |

## Presage bridge — `presage-bridge/`

| Feature | Status |
|---|---|
| Frame protocol (tested on the browser side), `useCustomInput` + `sendFrame` into the official SDK | ⚠️ SDK ready with a real key; live measurement not yet observed |
| Metrics, hints, status to the browser; stable vitals to the engine every 5 s; heartbeat | ⚠️ as above |
