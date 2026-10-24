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

## Not verified yet

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

- **Privacy:** video never leaves the device, but voice audio goes to ElevenLabs (or, without a key, to the browser
  vendor's speech service in Chrome / Edge), and note text goes to Google for Gemini.
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
  scored: NEWS2, alerts, the trend chart and the forecast use measured (Presage, crew) readings only.
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
- Python files aren't `ruff format`-ed (lint is clean); a repo-wide reformat was skipped to avoid merge conflicts
  while the team works in parallel.
- `docs/PRD.md` and `docs/CONCEPT.md` describe v1 and are kept for history.
