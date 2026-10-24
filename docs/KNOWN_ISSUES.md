# Known issues

Things the one-shot could not verify or deliberately simplified. Triage these first (log progress in `FEEDBACK.md`).

## Not verified on the build machine

- **Docker / TimescaleDB path never ran.** Docker Desktop's engine was not available, so `docker compose up`, both
  Dockerfiles and `PgRepo` (asyncpg + migrations + `vitals_1m` continuous aggregate) are untested. Everything was
  verified against the in-memory store, which implements the same `Repo` interface. First thing to do:
  `docker compose up`, then `TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/atollcare uv run pytest`
  (the API tests honour `TEST_DATABASE_URL`; they reset demo rows).
- **Real adapters untested** (no keys): Gemini (intake, SBAR, explanation, guidance), ElevenLabs (Scribe STT, TTS),
  Presage (`sdk`/`cloud` are placeholders marked `TODO(presage-verify)`), S3 storage. Mock paths are tested.
  - Gemini: uses `google-genai` `response_schema` with Pydantic classes; confirm `gemini-flash-latest` is a valid id.
  - ElevenLabs: default voice ids are public premade voices — set `ELEVENLABS_VOICE_GUIDE/STATUS` explicitly.
  - Presage: the browser records WebM; the SDK may need MP4 or raw frames. Confirm with the Presage booth.
- **Camera scan, microphone and offline queue** were built but not exercised in a real browser with devices / DevTools
  offline. Camera and mic need HTTPS (fine on Vultr via Caddy, fine on `localhost`).

## Simplifications

- Breach penalty is measured as `elapsed_since_window_start + total_min − window_min` (the PRD formula omits elapsed
  time, which would let a late case look in-window). Interim plans take the 3× penalty on the *interim* window and 1×
  on definitive-care delay, so the chosen interim plan also scores best (`core/decision.py::score_route`).
- Added `preferred_capabilities` (stroke → `stroke_unit`, IGMH only, −30 min bonus, only within window) so the stroke
  scenario starts at IGMH as the PRD story requires; without it the engine (correctly) prefers Kulhudhuffushi's
  airport-side hospital by 10 min. Team decision: keep, tune, or drop.
- Added Laamu link road (`gan_l_rh ↔ kadhdhoo`) as a ground link alongside the Hulhulé ↔ Malé bridge.
- Forecast extrapolation is capped at 2× the observed span, and parameters first measured later are back-filled, so
  a partial → complete NEWS2 jump is not read as deterioration. Copy is hedged.
- Automatic re-assessments (capacity, asset, demo-state changes) are debounced to once per 2 s per case — the
  trailing run lands ≤ 2 s later. Direct case mutations (intake, vitals, decline) assess immediately.
- Scan jobs and the guidance cache are in-memory (lost on engine restart); scan videos are not deleted by the app —
  rely on the S3 lifecycle rule (README).
- `pph_weather`: at sea state 6 nothing is feasible until the helicopter is toggled on — the engine says so
  explicitly. That is the intended "constraint reasoning" demo but the presenter must know to toggle the helicopter.
- Sim-clock times written to hypertables can be "in the future" relative to real time during a demo; the CAgg has
  real-time aggregation on, and the trend query falls back to raw rows.
- Map tiles default to OpenStreetMap's public tile server (CARTO now needs a key). Fine for a demo; set
  `NEXT_PUBLIC_MAP_TILES` for anything heavier.

## Rough edges

- No auth by design; the role switcher only sets the `X-Role` header used for timeline attribution.
- `Date.now()` drives the 10 s "pulse" highlight in the hospital inbox; rows that arrive while the tab is hidden
  won't pulse.
- Board/map pages fetch each active case individually every 2 s — fine for a demo, not for many cases.
- Engine pins the referred destination while a referral is pending; if it becomes incapable, the engine re-routes and
  re-sends (visible as a `replanned` event), even if the specialist had already accepted.
