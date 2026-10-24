# Known issues (v2)

What hasn't been verified, and what's deliberately simple. Log triage progress in `FEEDBACK.md`.

## Not verified

- **Live Presage measurement.** The official `@smartspectra/node-sdk` loads on Windows x64, and a dummy key
  exercised the auth-failure path. No real key was available, so HR / RR / HRV from a real face has not been seen
  end to end. First thing to do with a key: run the bridge, open `/crew/<id>` in Chrome or Edge, sit still 50–80 cm
  from the camera with face and upper chest in the guide, and check "Presage · live" values against a pulse oximeter.
- **Camera and microphone in a real browser.** All UI passes ran in a browser pane that blocks capture, so the live
  instrument (acquiring → measuring), the mic level meter and live dictation weren't seen working. The blocked,
  busy and no-camera states and the typed-note path were verified.
- **Browser speech recognition** (the fallback when ElevenLabs isn't configured) sends audio to the browser vendor's
  service in Chrome and Edge. Fine for a demo; use Scribe (`ELEVENLABS_MODE=real`) for anything else.
- **Real adapters** (no keys): Gemini SBAR + extraction, ElevenLabs Scribe + TTS, S3 storage. The mock and fallback
  paths are tested.
- **Docker / TimescaleDB.** Docker Desktop's engine wasn't available on the build machine, so `docker compose up`,
  both Dockerfiles and `PgRepo` (asyncpg, migrations, the `vitals_1m` continuous aggregate) have not run. Everything
  ran against the in-memory store, which implements the same `Repo` interface. To check:
  `docker compose up`, then `TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/atollcare uv run pytest`.

## Simplifications

- **No authentication.** Anyone with the URL can act as crew or hospital. Presenter tools are hidden behind a shortcut,
  not protected.
- **Polling, not push.** Both screens poll every 2 s (SWR). Hospital → crew questions can take up to ~2 s to appear.
- **One shared hospital view.** The rail lists every handed-off transfer, whatever its destination. There's no
  per-hospital inbox.
- **Rule-based extraction** (when Gemini is off) understands common drugs, doses, routes and a few procedures. It
  splits on clause boundaries, so "aspirin and GTN, oxygen 4 litres" gives three items, but unusual phrasing can be
  missed. The crew's own words are always kept beside the chips.
- **NEWS2 from contactless vitals is partial** until the crew adds SpO₂, BP, temperature and ACVPU. The UI says so and
  prompts "Complete NEWS2".
- **Simulated vitals** (demo signal) follow a profile picked from the complaint (for example, chest pain → HR rising
  over the journey), so trends and alerts have something to show. They're labelled everywhere and never posted as
  `presage`.
- **Sim clock.** Journeys run on an accelerated clock (presenter speed 1–60×). Times written to the database can be
  "in the future" relative to wall-clock time during a demo. The continuous aggregate has real-time aggregation on.
- **Map tiles** come from Esri's public World Light Gray service (English labels, no key). Fine for a demo.

## Rough edges

- The trend window is 60 sim-minutes. After a long fast-forward the oldest readings drop out of the chart.
- Closing the transfer is crew-side only; the hospital sees `arrived` until then.
- `docs/PRD.md` and `docs/CONCEPT.md` describe v1 (route optimiser, island reporter app) and are kept for history.
