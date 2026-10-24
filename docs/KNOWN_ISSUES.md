# Known issues (v2)

What hasn't been verified, and what's deliberately simple. Log triage progress in `FEEDBACK.md`.

## Verified so far

- **Real adapters:** Gemini writes the SBAR (`gemini-3.5-flash`, with `gemini-flash-lite-latest` as fallback — the
  default `gemini-flash-latest` was returning 503 under load). ElevenLabs text-to-speech and Scribe speech-to-text
  round-trip correctly ("Gave aspirin 300 milligrams…" → "Aspirin 300 mg", "GTN spray").
- **Camera and microphone in Chrome:** a teammate saw the camera feed and dictated a note in Chrome on Windows.
- **TimescaleDB:** the full engine suite (88 tests) passes against TimescaleDB 2.31 / Postgres 17 as well as the
  in-memory store; migrations, continuous aggregates, compression, insights and the benchmark all run.
- **Production images:** `docker compose -f docker-compose.prod.yml build` succeeds; the web and engine containers
  serve every page and proxy `/api` to the engine, which migrates and talks to TimescaleDB.
- **Pre-arrival → crew → hospital (branch `integration/part1`):** walked through in the browser at 390, 1024 and 1440 px
  wide with real Gemini and the real SmartSpectra SDK: packet created, account typed and condensed (age and sex taken
  from "She is 72"), a clip uploaded and scanned, sent, picked up by the crew, transfer started with everything carried
  over, a crew scan added (clips sent through the API: the pane blocks the camera), the hospital's Video tab and "Seen
  on video" rendered. Spoken accounts (Scribe) weren't exercised in this pass. 189 engine tests pass on both stores.
- **Clip measurement path:** engine → MJPEG → bridge `/vitals/file` → SmartSpectra runs end to end. On a test-pattern
  clip it correctly reports *No face found* (12 s for an 8 s clip), and Gemini answers *can't tell* for every sign.

## Not verified yet

- **A scan of a real face.** Every scan so far used a test pattern, so no heart or breathing rate has come back from a
  clip yet, and no sign has been "seen" with frames. Check: on a phone over HTTPS (the Vultr deploy or a tunnel),
  prop the phone up, record a teammate for 60 s, compare the result with a pulse oximeter.
- **Recording on a real phone.** The recorder (`MediaRecorder`, back camera, upload fallback) and the voice step were
  checked only in the desktop browser pane, which blocks the camera and microphone, so only typing and uploads were
  exercised. iOS Safari records MP4; the engine converts any format with ffmpeg, but it hasn't been tried.

- **Live Presage measurement.** The bridge reports the SDK `ready` with a real key, but nobody has yet watched HR / RR
  go to *Presage · live* on a real face. Check: run the bridge, open `/crew/<id>` in Chrome, sit still 50–80 cm from
  the camera with face and upper chest in the guide, compare against a pulse oximeter.
- **Tiger Cloud specifically.** Everything Tiger-related ran against self-hosted TimescaleDB 2.31; the same SQL should
  run on Tiger Cloud, but it hasn't been pointed at a Tiger Cloud service yet.
- **Vultr deployment.** The runbook (`DEPLOY_VULTR.md`), deploy script and images are ready; the instance hasn't been
  created. The Vultr metadata lookup that shows the region is untested on a real instance (`HOST_LABEL` is the
  fallback).
- **Vultr Object Storage** for cached TTS audio (`STORAGE_MODE=s3`).

## Honest limits to say out loud

- **Privacy:** the live camera's video never leaves the vehicle. A **scan's clip does leave the phone**: it goes to the
  engine, which sends frames to Google (Gemini) and the clip to the Presage bridge, keeps it in memory only, and stores
  just the frames a finding cites. ID photos go to Google too. Voice audio goes to ElevenLabs (or Gemini, or the browser
  vendor's speech service), and note text goes to Google for Gemini.
- **Gemini's sign check is a checklist, not an examination.** Every "seen" cites frames the hospital can look at;
  "couldn't tell" is never shown as "not there". The 12-sign catalogue is a demo assumption, not a validated list.
- **Two quality thresholds:** readings below 0.6 are shown but not scored (engine); Percy's extractor calls below 0.4
  "uncalibrated". The scan card shows both bands ("weak signal" 0.4–0.6, "unreliable" below 0.4). Pick one.
- **Working impression without Gemini is a keyword match** on the crew's words ("face drooping" → *Suspected
  stroke*). It's not a diagnosis; the hospital screen says where it came from and quotes the words.
- **Presage needs stillness.** In a moving vehicle readings will be noisier; the camera shows Presage's own framing
  and movement hints, and readings above 110 BPM are flagged *confirm with a monitor*.

## Simplifications

- **No authentication.** Anyone with the URL can act as crew or hospital. Presenter tools are behind a shortcut, not
  protected.
- **Polling, not push.** Screens poll every 2 s (insights every 30 s).
- **One shared hospital view.** The rail lists every handed-off transfer, whatever its destination.
- **Simulated vitals** keep the demo moving without a Presage key. They're labelled everywhere, rendered muted, never
  scored: NEWS2, alerts, the trend chart and the forecast use measured (Presage, crew) readings only. In scan mode
  nothing is simulated, and an old simulated number stops being shown.
- **Pre-arrival packets have no login or link-sharing.** Anyone with the packet's URL can edit it until it's sent; the
  crew list shows every sent packet in the region.
- **One bridge, one SmartSpectra session:** a clip takes over a live camera session while it's measured.
- **Seeded network history** (`Seed 60 days of history`) is simulated data for the insights page, flagged `seeded`,
  hidden from both clinical screens and kept by *Clear live transfers*. The insights page says when it's included.
- **Rule-based extraction** (without Gemini) knows common drugs, doses, routes and a few procedures, and reads
  spoken units ("300 milligrams"). Unusual phrasing can be missed; the crew can strike anything wrong.
- **NEWS2 is partial** until the crew add SpO₂, BP, temperature and ACVPU.
- **Sim clock:** journeys run on an accelerated clock (1–60×).
- **Map tiles:** Esri's public World Light Gray service (English labels, no key).

## Rough edges

- The clinical trend window is 60 sim-minutes; after a long fast-forward the oldest readings drop off the chart.
- Closing a transfer is crew-side only.
- Gemini's sign check takes 20–50 s per clip with `GEMINI_VQA_THINKING=low` (up to two minutes with the model's
  default); the screens show progress, and Presage's numbers usually land first.
- A packet started as a transfer before its scan finished gets the scan's readings and timeline line when it finishes;
  the line is dated when the clip was recorded, so it sorts before the transfer started.
- Python files aren't `ruff format`-ed (lint is clean); a repo-wide reformat was skipped to avoid merge conflicts
  while the team works in parallel.
- `docs/PRD.md` and `docs/CONCEPT.md` describe v1 and are kept for history.
