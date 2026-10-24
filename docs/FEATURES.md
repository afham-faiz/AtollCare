# Feature checklist (v2: two screens)

✅ built and exercised · ⚠️ built, not verified end to end (see the note) · ❌ not built.

**How it was verified:** 81 engine tests (`engine/tests`); `scripts/demo_e2e.py` against a live engine (in-memory
store, mock adapters); `bun run typecheck`, `lint` and `build`; manual browser passes of the full story at
1440×900, 1024×768 and 390×844 (plus ~800 px), in a browser where **camera and microphone were blocked**. Live capture
paths therefore show ⚠️ below.

## Crew screen — `/crew`, `/crew/[transferId]`

| Feature | Status | Files |
|---|---|---|
| Start a transfer: "What's happening" (type or dictate), age, sex, from → to, transport | ✅ | `crew/CrewStartClient.tsx` |
| In-progress list on the start screen | ✅ | `crew/CrewStartClient.tsx` |
| Monitor hierarchy: patient + status → camera instrument → vitals → note dock → next action | ✅ | `crew/[transferId]/CrewClient.tsx` |
| Camera instrument: face + upper-chest guide, acquiring sweep, status capsule, framing hints, 30 s breathing settle | ⚠️ camera blocked in the test browser; empty/blocked/busy/no-camera states verified | `CameraInstrument.tsx`, `lib/presage.ts` |
| Presage live HR / RR / HRV + breathing waveform; >110 BPM flagged "confirm with a monitor" | ⚠️ needs a real `PRESAGE_API_KEY` and a camera | `VitalsPanel.tsx`, `BreathingWave.tsx` |
| Labelled demo signal when Presage isn't live (both screens, SBAR) | ✅ | `VitalsPanel.tsx`, `core/briefing.py`, `adapters/gemini.py` |
| Crew-entered SpO₂ / BP / temp / ACVPU with freshness; "Complete NEWS2" prompt | ✅ | `VitalsSheet.tsx`, `VitalsPanel.tsx` |
| Alerts (NEWS2 band, HR trend, forecast) with "+N more" | ✅ | `VitalsPanel.tsx`, `core/alerts.py` |
| Voice note: tap, speak, tap; real mic level meter; live transcript; "Structuring note…" → chips | ⚠️ mic blocked in the test browser; typed path verified | `VoiceCapture.tsx`, `lib/dictation.ts`, `lib/audio.ts` |
| Typed notes stored as `text`, dictated as `voice` (provenance) | ✅ | `VoiceCapture.tsx` |
| Hospital question lands on the mic ("IGMH asks · …"); answer by voice or typing | ✅ (typed) | `VoiceCapture.tsx`, `CrewClient.tsx` |
| Review + send handoff (urgency, key vitals with source, demo-signal disclaimer, SBAR) | ✅ | `HandoffSheet.tsx` |
| Hospital acceptance + its message shown in the dock; "Arrived" → "Close transfer" | ✅ | `CrewClient.tsx` |
| Hospital messages and alerts read aloud once ("Voice on" / "Muted") | ⚠️ browser speech untested audibly; ElevenLabs TTS untested | `lib/speech.ts` |
| Notes and messages timeline sheet | ✅ | `components/(transfer)/Timeline.tsx` |

## Hospital screen — `/hospital`, `/hospital/[transferId]`

| Feature | Status | Files |
|---|---|---|
| Incoming rail: urgency rule, ETA, NEWS2, "Needs response", question count, fresh-arrival highlight + toast | ✅ | `hospital/HospitalClient.tsx` |
| Only handed-off transfers appear (not `preparing`) | ✅ (API test + e2e) | `services/transfers.py` |
| Hero: suspected condition, patient, urgency + status, alerts; arrival time; **Accept transfer** | ✅ | `hospital/TransferDetail.tsx` |
| Layout by container width (rail-aware): hero band, 3/6-column vitals, sticky decision bar on phones | ✅ | `hospital/Hospital.module.scss` |
| Vitals strip with status word, source and freshness; demo signal tagged | ✅ | `TransferDetail.tsx` |
| Handoff tab: SBAR + "Given" list + provenance line | ✅ | `components/(transfer)/SbarDocument.tsx` |
| Trend tab (Tiger Data aggregate in Postgres; raw readings in memory mode) | ✅ memory · ⚠️ Timescale | `TrendChart.tsx`, `db.py` |
| Ask the crew (free text + suggestions), Q&A thread | ✅ | `TransferDetail.tsx` |
| Accept: clinician, what's being prepared, message to the crew | ✅ | `hospital/AcceptModal.tsx` |
| Transport tab: map (Esri light grey, English labels) + facts | ✅ | `TransferMap.tsx` |

## Engine

| Feature | Status | Files |
|---|---|---|
| Lifecycle `preparing → pending → accepted → arrived → closed`; idempotent handoff; accept requires pending | ✅ | `services/transfers.py`, `routers/transfers.py` |
| NEWS2 (partial / complete), deterioration forecast (OLS), alerts with hysteresis + re-announce cooldown | ✅ | `core/news2.py`, `core/forecast.py`, `core/alerts.py` |
| SBAR: Gemini (JSON schema) with template fallback; "(demo signal)" labelling | ✅ template · ⚠️ real Gemini untested | `core/briefing.py`, `adapters/gemini.py` |
| Intervention / observation extraction (clause-by-clause rules; Gemini when configured) | ✅ rules · ⚠️ Gemini | `core/briefing.py` |
| Scribe STT, TTS with storage cache | ⚠️ untested without a key | `adapters/elevenlabs.py` |
| Region packs + prepared demo cases (Maldives × 2, Western Isles × 1) | ✅ | `data/regions/*.json`, `core/regions.py` |
| Sim clock, SimLoop (progress, ETA, simulated vitals when not live, auto-arrive) | ✅ | `core/clock.py`, `sim/loop.py` |
| Postgres / TimescaleDB repo + migrations | ⚠️ never run (no Docker on the build machine) | `db.py`, `migrations/001_init.sql` |

## Presage bridge — `presage-bridge/`

| Feature | Status |
|---|---|
| WebSocket frame protocol (RGBA, 16-byte header), `useCustomInput` + `sendFrame` into the official SDK | ⚠️ SDK loads on Windows x64; auth-failure path verified with a dummy key; no live measurement yet |
| Metrics, validation hints and status back to the browser; stable vitals posted to the engine every 5 s | ⚠️ as above |
| Heartbeat to the engine (`/api/presage/heartbeat`) and `no_api_key` / offline states in the UI | ✅ |

## Presenter tools (not part of either screen)

| Feature | Status | Files |
|---|---|---|
| Presenter panel (Ctrl / ⌘ + .), `/demo`: prepared cases with suggested line, region, speed, services, reset | ✅ | `components/(shell)/PresenterPanel.tsx`, `PresenterTools.tsx` |
