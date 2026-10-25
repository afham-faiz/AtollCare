# Known issues (v3)

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
- **Clip measurement path:** engine → MJPEG (constant 30 fps, from the original upload) → bridge `/vitals/file` →
  SmartSpectra runs end to end. On a test-pattern clip it correctly reports *No face found* (12 s for an 8 s clip).
- **Live phone path:** JPEG frames → the web app's `/presage/ws` (Next proxy) → bridge → SmartSpectra runs end to end
  with `presage-bridge/scripts/replay.mjs`: 240 frames in 8 s, framing hints back at once, the summary (traces,
  framing intervals) on stop. The engine stores a live summary sent with the clip and only runs Gemini on it.
- **FDA clearance details** checked against the 510(k) summary K254169 (18 June 2026): pulse 50–150 bpm and
  respiratory rate 8–26 /min over a 30 s window, healthy adults 18–70, phone in a static mount, trained staff, not
  for critical care. Maldives ambulance 102 (two embassies and the CIA Factbook agree).

## Not verified yet

- **A real face, live, on a real phone.** The most important open item. Every measurement so far used a test
  pattern, so no heart or breathing rate has come back from either path. Check (see `PITCH.md` → Hour 0):
  `scripts/phone_tunnel.sh`, scan the presenter QR, prop the phone up, measure a teammate with a fingertip oximeter on.
- **JPEG frames vs Presage's accuracy.** Each frame is a JPEG at quality 0.9, 640 px on the long side. Per-frame JPEG
  keeps each frame's colour (no inter-frame smoothing), but whether it costs accuracy against raw frames is untested.
  Compare a replayed clip at JPEG vs the file path on the same recording.
- **Uplink.** The phone sends roughly 1 MB/s at 30 fps through the tunnel; on a weak uplink frames are dropped (never
  queued), which lowers the frame rate Presage sees. Use our own hotspot on stage.
- **Recording on a real phone** (camera, microphone for "film and speak", iOS Safari MP4). The desktop browser pane
  blocks both, so only uploads and typing were exercised.
- **Exposure lock** (`applyConstraints` exposure/white balance after 2 s) is attempted where the camera says it can;
  untested on real phones.

- **Tiger Cloud specifically.** Everything Tiger-related ran against self-hosted TimescaleDB 2.31; the same SQL should
  run on Tiger Cloud, but it hasn't been pointed at a Tiger Cloud service yet.
- **Vultr deployment.** The runbook (`DEPLOY_VULTR.md`), deploy script and images are ready; the instance hasn't been
  created. The Vultr metadata lookup that shows the region is untested on a real instance (`HOST_LABEL` is the
  fallback).
- **Vultr Object Storage** for cached TTS audio (`STORAGE_MODE=s3`).

## Honest limits to say out loud

- **Privacy:** a phone scan's picture leaves the phone: frames stream to the Presage bridge (on our laptop or server)
  and the clip goes to the engine, which sends still frames to Google (Gemini), keeps the clip in memory only, and
  stores just the frames a finding cites. ID photos go to Google too. Voice and the video's sound go to ElevenLabs (or
  Gemini) for transcription, and note text to Google for Gemini. Presage's native mobile SDK would keep the picture on
  the phone; that's the next step, not done.
- **Outside the clearance, and said so.** K254169 is for healthy adults, spot checks, a mounted phone, trained staff.
  Our crew scan copies the setup; the patients aren't healthy and a boat moves. Hence: the companion's video is a
  bystander estimate (never scored), a camera reading alone never raises a critical alert, readings outside 50–150 /
  8–26 are flagged, and the crew's oximeter pulse is checked against the camera.
- **Gemini's sign check is a checklist, not an examination.** Every "seen" cites frames the hospital can look at;
  "couldn't tell" is never shown as "not there". The 12-sign catalogue is a demo assumption, not a validated list.
- **Working impression without Gemini is a keyword match** on the crew's words ("face drooping" → *Suspected
  stroke*). It's not a diagnosis; the hospital screen says where it came from and quotes the words.
- **Presage needs stillness.** In a moving vehicle readings will be noisier; the phone shows Presage's own framing and
  movement hints live, and each scan's report shows when the shot wasn't usable and why.
- **The camera trend needs two stable crew scans at least 2 minutes apart.** It compares the first and the latest;
  big rises are a prompt for a manual set, not a diagnosis.
- **Gemini's free quota runs out.** During testing the sign check hit `429 RESOURCE_EXHAUSTED`; the scan card then says
  "Gemini's usage limit was reached" and Presage is unaffected. Use a paid key on stage.

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
- **One bridge, one SmartSpectra session:** a scan (live or clip) pauses a continuous monitor session, which resumes
  by itself afterwards. Two phones scanning at once take turns.
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
