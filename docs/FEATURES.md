# Feature checklist

✅ built and exercised (tests, e2e script or browser) · ⚠️ built but not fully verified, or a real-service path is
best-effort. Paths are relative to the repo root. Keep this file current — it is the shared progress board.

Verification in the one-shot: 85 engine tests (`engine/tests`), `scripts/demo_e2e.py` against a live engine (memory
store), `bun run typecheck / lint / build`, and manual browser passes of `/demo`, `/report/[id]` (desktop + 375 px),
`/hospital/[id]` (decline → re-route), `/transport`, `/transport/[id]`, `/demo?view=split`. All with mock adapters.

## M1 — Island Reporter App (Lane B)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M1.1 | One-tap alert | ✅ | `web/src/app/(main)/report/ReportClient.tsx`, `engine/app/routers/cases.py` |
| F-M1.2 | Describe (text or voice) → intake chips, quick answers | ✅ (voice only with mock STT) | `web/src/app/(main)/report/[caseId]/DescribePanel.tsx`, `components/(case)/IntakeChips.tsx` |
| F-M1.3 | Patient details, PATCH on blur | ✅ | `report/[caseId]/PatientPanel.tsx` |
| F-M1.4 | Vitals capture + live NEWS2 (AC: 17 / high) | ✅ | `report/[caseId]/VitalsPanel.tsx`, `components/(vitals)/ManualVitalsForm.tsx`, `components/(case)/News2Card.tsx` |
| F-M1.5 | Submit & see recommendation | ✅ | `report/[caseId]/ReportCaseClient.tsx`, `components/(case)/RouteCard.tsx` |
| F-M1.6 | Clinician referral (override, SBAR preview, note) | ✅ | `report/[caseId]/ReferralPanel.tsx` |
| F-M1.7 | First-aid guidance with voice | ✅ (browser speech in mock; ElevenLabs path untested) | `report/[caseId]/GuidancePanel.tsx`, `lib/speech.ts` |
| F-M1.8 | Live status for family + QR link | ✅ | `components/(case)/FamilyStatus.tsx`, `components/(case)/StatusStepper.tsx`, `(main)/case/[caseId]` |
| F-M1.9 | Respond to info requests | ✅ (API test; UI built) | `report/[caseId]/InfoRequestPanel.tsx` |
| F-M1.10 | Offline-tolerant draft + retry queue | ⚠️ not tested with DevTools offline | `web/src/lib/offline.ts` |

## M2 — Decision Engine (Lane A)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M2.1 | Orchestrator / re-assessment + debounce | ✅ | `engine/app/core/decision.py`, `engine/app/services/cases.py` |
| F-M2.2 | Structured intake (Gemini) + rule fallback | ✅ fallback · ⚠️ real Gemini untested (no key) | `engine/app/adapters/gemini.py`, `engine/app/core/fallback_intake.py` |
| F-M2.3 | NEWS2 (every boundary tested) | ✅ | `engine/app/core/news2.py`, `engine/tests/test_news2.py` |
| F-M2.4 | Conditions, windows, capabilities, severity | ✅ | `engine/app/core/conditions.py`, `engine/app/data/conditions.yaml` |
| F-M2.5 | Routing + scoring & choice | ✅ (all §8.9 scenario assertions pass) | `engine/app/core/routing.py`, `engine/app/core/decision.py`, `engine/app/data/transport_modes.yaml` |
| F-M2.6 | Deterioration forecast | ✅ | `engine/app/core/forecast.py`, `components/(case)/VitalsChart.tsx` |
| F-M2.7 | SBAR (Gemini) + template | ✅ template · ⚠️ Gemini untested | `engine/app/core/summary.py`, `components/(case)/SbarSummary.tsx` |
| F-M2.8 | Route explanation (Gemini) + template | ✅ template · ⚠️ Gemini untested | `engine/app/core/decision.py::template_explanation`, `services/cases.py::_explain` |
| F-M2.9 | Baseline comparison / headline | ✅ | `engine/app/core/baseline.py`, `engine/app/core/summary.py::headline`, `engine/app/data/baseline.yaml` |
| F-M2.10 | Engine inspector | ✅ | `components/(case)/EngineInspector.tsx` |

## M3 — Hospital / Specialist (Lane C)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M3.1 | Referral inbox (sort, window remaining, pulse) | ✅ | `web/src/app/(main)/hospital/HospitalClient.tsx` |
| F-M3.2 | Case review | ✅ | `hospital/[caseId]/HospitalCaseClient.tsx` |
| F-M3.3 | Accept / Decline / Request info | ✅ | `hospital/[caseId]/ResponseActions.tsx` |
| F-M3.4 | Info Q&A thread | ✅ | `hospital/[caseId]/HospitalCaseClient.tsx` |
| F-M3.5 | Auto re-plan on decline + toast | ✅ | `services/cases.py::respond`, `lib/useEventToasts.ts` |
| F-M3.6 | Case notes | ✅ | `hospital/[caseId]/HospitalCaseClient.tsx` |
| F-M3.7 | Close case | ✅ | `services/cases.py::close` |
| F-M3.8 | Capacity panel → re-plan (AC: CT off flips stroke to Kulhudhuffushi) | ✅ | `hospital/CapacityPanel.tsx`, `services/world.py` |
| F-M3.9 | Time-saved panel + assumptions | ✅ | `components/(case)/TimeSavedPanel.tsx` |

## M4 — Transport (Lane C)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M4.1 | Dispatch board | ✅ | `web/src/app/(main)/transport/TransportClient.tsx` |
| F-M4.2 | Dispatch (route + asset override) | ✅ | `transport/[caseId]/TransportCaseClient.tsx`, `services/cases.py::dispatch` |
| F-M4.3 | Live map | ✅ | `components/(map)/AtollMap.tsx` |
| F-M4.4 | Transport simulator (restart-safe schedule) | ✅ | `engine/app/sim/transport_sim.py` |
| F-M4.5 | Arrival & handover | ✅ | `services/cases.py::_complete_arrival` |
| F-M4.6 | Asset roster | ✅ | `transport/AssetRoster.tsx` |
| F-M4.7 | Weather & daylight banner | ✅ | `components/WeatherBanner.tsx`, `services/world.py::clock_info` |
| F-M4.8 | Crew audio brief | ✅ (browser speech in mock) | `routers/voice.py`, `core/summary.py::crew_brief` |

## M5 — Voice (Lane A / B)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M5.1 | Speech-to-text (Scribe) | ✅ mock · ⚠️ real untested | `engine/app/adapters/elevenlabs.py`, `components/(voice)/VoiceRecorder.tsx` |
| F-M5.2 | Text-to-speech, cached by hash | ✅ mock/browser · ⚠️ real untested | `adapters/elevenlabs.py::speak`, `components/(voice)/AudioPlayer.tsx` |
| F-M5.3 | Vetted guidance library (LLM selects/orders only) | ✅ | `engine/app/data/first_aid.yaml`, `services/cases.py::guidance` |
| F-M5.4 | Language selector (Dhivehi: text only) | ✅ | `routers/meta.py::LANGUAGES`, `report/[caseId]/GuidancePanel.tsx` |

## M6 — Contactless vitals (Lane A / B)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M6.1 | Camera scan UI | ⚠️ built; not exercised with a real camera here | `components/(vitals)/CameraScan.tsx` |
| F-M6.2 | Scan processing (sdk / cloud / mock / manual) | ✅ mock · ⚠️ sdk/cloud are `TODO(presage-verify)` | `engine/app/adapters/presage.py`, `engine/app/services/scans.py` |
| F-M6.3 | Continuous monitoring | ⚠️ built, untested | `CameraScan.tsx` (Monitor toggle) |
| F-M6.4 | Quality gating (< 0.6 excluded) | ✅ | `core/news2.py::latest_values`, `db.py`, `CameraScan.tsx` |

## M7 — Platform (shared)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M7.1 | Local dev via docker compose | ⚠️ written, not run (Docker unavailable on build machine); no-Docker path verified | `docker-compose.yml`, `engine/Dockerfile`, `web/Dockerfile` |
| F-M7.2 | Tiger Data migrations / hypertables / CAgg | ⚠️ SQL written, Postgres path not executed here; memory store verified | `engine/app/migrations/*.sql`, `engine/app/db.py::PgRepo` |
| F-M7.3 | Vultr deploy (compose + Caddy + script) | ⚠️ not deployed | `docker-compose.prod.yml`, `Caddyfile`, `scripts/deploy_vultr.sh` |
| F-M7.4 | Object storage (s3 / local) | ✅ local · ⚠️ s3 untested | `engine/app/adapters/storage.py`, `routers/meta.py::media` |
| F-M7.5 | Health & adapter status | ✅ | `routers/meta.py`, `components/Footer.tsx` |
| F-M7.6 | Type generation | ✅ | `web/package.json` (`gen:api`), `engine/app/openapi_dump.py`, `web/src/lib/api-types.ts` |
| F-M7.7 | Error handling + fallback notes | ✅ | `engine/app/main.py`, `web/src/lib/api.ts`, `web/src/lib/toast.ts` |
| F-M7.8 | Structured JSON logs with case_id | ✅ | `engine/app/logging_setup.py` |

## M8 — Demo control (Lane C)

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M8.1 | Reset | ✅ | `services/world.py::reset`, `demo/DemoClient.tsx` |
| F-M8.2 | World controls | ✅ | `demo/WorldControls.tsx`, `core/clock.py` |
| F-M8.3 | Scenarios + Autoplay | ✅ (all five load and assess; hero autoplays to dispatch) | `engine/app/data/scenarios/*.json`, `services/scenarios.py` |
| F-M8.4 | Presenter split view | ✅ | `demo/PresenterView.tsx` |

## M9 — Docs & pitch

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M9.1 | README | ✅ | `README.md` |
| F-M9.2 | PITCH.md | ✅ | `docs/PITCH.md` |
| F-M9.3 | DEV_POST.md draft | ✅ draft · team to publish | `docs/DEV_POST.md` |
| F-M9.4 | FEATURES / KNOWN_ISSUES | ✅ | `docs/FEATURES.md`, `docs/KNOWN_ISSUES.md` |

## M10 — Landing & shared UI

| ID | Feature | Status | Files |
|---|---|---|---|
| F-M10.1 | Landing page | ✅ | `web/src/app/(main)/LandingClient.tsx` |
| F-M10.2 | Header (scroll-aware, role switcher, hamburger) | ✅ | `components/Header.tsx` |
| F-M10.3 | Case timeline | ✅ | `components/(case)/CaseTimeline.tsx` |
| F-M10.4 | Dark mode (system + toggle) | ✅ | `styles/globals.css`, `app/layout.tsx`, `components/Header.tsx` |
