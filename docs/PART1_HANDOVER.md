# Part 1 handover: where things stand and what comes next

A distilled record of the Part 1 prototype (pre-arrival at the health centre), written so the next phase can start
without re-reading the history. Facts here were checked in the code or by running it; anything unverified is
marked **UNVERIFIED**.

## 1. What Part 1 does today

A local demo page (`python run.py --serve`, or `start.bat`) with three boxes and a collapsed developer panel.

| Box | Input | How | Model or provider | Output |
|---|---|---|---|---|
| **1. Video** | an uploaded video, or a browser camera recording (video only) | shrink once with ffmpeg, then in parallel: Presage and the Gemini sign check | Presage SmartSpectra SDK (not an LLM), and `GEMINI_VQA_MODEL` | heart and breathing rate with a quality each; 12 visible signs (seen, not seen, cannot assess) with confidence, reason and evidence frames; "mentioned in the account but not seen" |
| **2. Voice** | live microphone, or an audio or video file | browser audio is streamed to the server and cut into sentences at pauses; each goes to Gemini. A file is sent whole | `GEMINI_STT_MODEL` (currently `gemini-3.8-flash`) | transcript, which becomes the "account" that marks which signs were mentioned |
| **3. ID** | a photo of an ID | Gemini vision with a JSON schema; code joins the name, checks the number's shape and works out the age | `GEMINI_ID_MODEL` | name, ID number, age, document type, `needs_review`, notes |

Not built: the final recommendation (urgency, what to prepare), slurred-speech detection (needs the audio itself),
signs that depend on movement, and a clinically validated sign list. The hand-off to the crew app is built
(section 5).

### Presage in detail
- Python sends the shrunken video to a Node service (`presage-sidecar/server.js`, port 3001). It converts it to an
  MJPEG `.avi` (the SDK cannot open H.264 `.mp4`) and runs `@smartspectra/node-sdk` 3.4.0 with `useFile`, played in
  **real time** (`interframeDelayMs: 33`; faster playback drops frames and loses the face).
- The SDK emits roughly one measurement per frame (value, confidence 0 to 100, stable flag) plus camera-check codes
  (`kFaceNotForward`, `kChestNotVisible`, `kExcessiveMotion` and so on). The sidecar returns the whole trace.
- `summarise_series` (`src/services/rppg_extractor.py`) takes the **median of the stable samples over the whole
  clip**, never the last sample (the final seconds are unreliable). Quality per vital is the mean confidence; the
  overall score is the weaker vital; below 0.4 counts as uncalibrated.
- Needs: face and upper chest in view, steady camera, patient still and quiet, well lit, 45 to 60 s. Talking
  invalidates the breathing rate. Gives no oxygen level, blood pressure or temperature.

## 2. How it is built

```
browser page (src/static/index.html)  ──►  FastAPI (src/app.py, port 8000)
                                              ├─ video_analysis.py ─► Presage sidecar (Node, 3001) ─► SmartSpectra SDK
                                              │                  └─► vqa_evaluator.py ─► Gemini (google-genai)
                                              ├─ transcription.py ─► Gemini        ├─ ocr_service.py ─► Gemini
                                              └─ logs/*.json  recordings/  (git-ignored)
```
- Every Gemini call goes through `src/services/gemini_client.py`: `GEMINI_USE_ENTERPRISE` picks AI Studio or Agent
  Platform keys, and `GEMINI_TIMEOUT_S` / `GEMINI_RETRY_ATTEMPTS` stop a stalled request hanging the page.
- Visual signs: `VQA_MODE=one_pass` (one request: frames, account and all 12 signs, each answered separately in two
  independent parts) or `two_step` (a planner reads only the account, an inspector sees only the frames).
  **Grounding is enforced in code:** a sign can only be "seen" if it cites real frames, and a "mentioned" needs a
  quote that appears in the account. The cue list is `src/data/cue_catalogue.json` (a demo assumption).
- Fail-soft everywhere: `parse_identity_doc`, `extract_vitals_from_video`, `plan_cues` and the inspector return
  empty results with a reason in `issues` instead of raising.
- Claude is not used anywhere in the app.

## 3. Settings (all in `inputs/.env`, none in code)

`src/config.py` has no default model names or numbers. A missing required setting raises `ConfigError` naming the
line to add. Template: `env.example`. `inputs/` is git-ignored, so keys never get committed.

`PRESAGE_MODE`, `PRESAGE_API_KEY`, `GEMINI_API_KEY`, `GEMINI_USE_ENTERPRISE`, `GEMINI_TIMEOUT_S`,
`GEMINI_RETRY_ATTEMPTS`, `GEMINI_STT_MODEL`, `GEMINI_STT_FALLBACK_MODEL`, `GEMINI_CHAT_MODEL`, `GEMINI_ID_MODEL`,
`GEMINI_CUE_PLANNER_MODEL`, `GEMINI_VQA_MODEL`, `VQA_MODE`, `VQA_FRAME_INTERVAL_S`, `VQA_MAX_FRAMES`,
`VIDEO_RECORD_MAX_S`, `TRANSCRIBE_LANGUAGE`, `STT_SILENCE_STOP_S`, `STT_FLASH_PAUSE_S`, `STT_FLASH_MAX_SEGMENT_S`,
`SAVE_RECORDINGS`, and for the hand-off `ENGINE_URL`, `ENGINE_WEB_URL`, `ENGINE_TIMEOUT_S`,
`HANDSHAKE_PATIENT_LABEL`, `GEMINI_SUMMARY_MODEL`, `HANDSHAKE_SEND_CONSCIOUSNESS`,
`HANDSHAKE_CONSCIOUSNESS_MIN_CONFIDENCE`.

## 4. Run and test

```powershell
.\.venv\Scripts\Activate.ps1
python run.py --serve            # page at http://127.0.0.1:8000 (starts the Presage sidecar itself)
python run.py clip.mp4           # one video from the command line
python scan_id.py card.jpg       # read an ID photo
python transcribe_file.py note.m4a
python visual_cues.py clip.mp4 --latest
python -m pytest                 # 183 tests, no keys, nothing sent to Google
```
Tests use `tests/conftest.py`, which fixes every setting and redirects logs and recordings to temp folders, so they
never touch your key or real data. Setup from scratch is in the README.

## 5. Hand-off to the crew app (built)

The teammate's app is on `origin/main` (branch `one-shot/build`, pull request #1): a FastAPI engine in `engine/`,
a Next.js crew and hospital app in `web/`, and a live-frame Presage bridge in `presage-bridge/`. A dry-run merge
with `user-branch` conflicts only on `README.md` and `.gitignore`.

**What was built (box 4 on the page, `/api/handshake/*`):**
- `src/services/packet.py`: `build_packet()`, a pure function that extracts the salient items from the ID result,
  the voice account digest, the Presage readings and the sign check.
- `src/services/account_digest.py`: one Gemini request gives a one-line complaint plus the full account with names
  and ID numbers removed; code then masks any run of 4 or more digits. If Gemini fails, only the masked one-line
  summary is sent and the full account is held back.
- `src/services/engine_client.py`: creates the transfer, sets monitoring, posts each reading and each note against
  `ENGINE_URL`. It never raises; every step reports ok or a plain reason. It never calls handoff, accept or arrive.
- The page previews the packet (sent, held back on purpose, missing), lets the crew pick From, To and Transport from
  their `/api/meta`, and sends only on an explicit click. Each hand-off is logged to `logs/handshakes.json`.

**What is sent and what is not:**

| Part 1 output | Sent to their input |
|---|---|
| ID age | `patient.age` |
| ID name | `patient.label` as initials (`HANDSHAKE_PATIENT_LABEL`); the name, **ID number** and date of birth are never sent |
| voice account | `complaint` (one line) and a note with the redacted full account |
| heart rate, breathing rate | two `source=presage` readings, each with its own confidence and a `hint` for camera problems. Mock or unavailable readings are never sent |
| ID card | a note describing the card (type, age, specimen flag), with no name or number |
| visual signs | one note: seen, not seen, could not assess, mentioned but not seen. Evidence images are not sent (their notes cannot carry them) |
| "alert and responsive" seen | `consciousness = "A"` only if `HANDSHAKE_SEND_CONSCIOUSNESS=true` and confidence is high enough. **Off by default:** their app only has the sources presage, manual and simulated, so an AI video impression would show as a crew entry |

The packet also lists what is missing (for example oxygen level, blood pressure and temperature are never measured by
Part 1), so the crew do not assume an absent value was normal.

**Facts about their API that shaped the design** (all confirmed by running it):
1. The journey clock **starts when a transfer is created**, so we create it only on an explicit send, and leave it in
   `preparing` for the crew to send the handoff.
2. New transfers get **simulated vitals** unless monitoring is set to `presage` or `off`; we set it.
3. Their readings under confidence 0.6 are kept but excluded from NEWS2 (ours cutoff is 0.4), so each reading goes
   with its own confidence.
4. Their error messages (unknown facility, same place, mode not available) are surfaced as they are.
5. Our page and their engine both default to port 8000. Run theirs on 8010 (`ENGINE_URL`).

**Verified against their REAL engine** (extracted with `git archive origin/main engine`, run with mock adapters and
an in-memory store on port 8010): create, monitoring, both readings, three notes, the three error messages, and the
whole flow driven from the page. Read back from their API, the transfer held label "D. M.", age 36, status
`preparing`, monitoring `presage`, two stored readings and three crew notes. A scan of everything their engine held
found no name, ID number, date of birth, or the health card number spoken in the call.
**UNVERIFIED:** their Next.js crew and hospital screens were never run, so how our transfer looks there, and what
their NEWS2, alerts and SBAR do with partial vitals, was not seen. Their real Gemini and ElevenLabs paths were not
exercised (mock adapters only).

To run their engine locally: `git fetch origin`, then `python run_crew_engine.py` (copies `engine/` from `origin/main` into the
git-ignored `.crew-engine/`, builds its own venv, starts it on the port in `ENGINE_URL` with mock adapters and an in-memory
store; `--refresh` takes a new copy). The page's box 4 shows a clear message when the server behind it is older than
the page (a 404 on `/api/handshake/*`) and a "Collected so far" line for what each box has produced.

## 6. Known issues and honest limits

- **Presage accuracy is unvalidated** against a reference device. A moving subject gave a breathing rate of 7, which
  is not believable. The 0.4 "calibrated" cutoff is lenient.
- **Badge wording:** "Alert and responsive" shows as an amber "Seen", which reads as a warning though it is the
  normal state. It needs a normal-or-concerning flag in the catalogue.
- **Still frames cannot show motion** (gaze tracking, arm drift, breathing rate), and a sign "not seen" may simply
  not have been in view. The model sometimes cites frame numbers that do not exist; the code drops them.
- **Google can stall.** One request hung for over six minutes before the timeout setting existed. The SDK may not
  retry a timeout automatically (**UNVERIFIED**); pressing Analyse again works.
- **`gemini-3.8-live` is refused** (`1007`/`1008`) for express-mode API keys. The Live code path exists but is
  unused; speech uses a flash model.
- **Flash can invent words from non-speech audio.** The prompt asks for `NO_SPEECH` and the code filters it, but
  this was only tested with a pure tone.
- **Camera and microphone only work on `localhost` or HTTPS.** A phone opening the page by the laptop's IP cannot record.
- **A 4K upload is slow** (hundreds of MB, then a 20 to 30 s shrink).
- **Redaction relies on Gemini.** Names cannot be removed deterministically; only digit runs are masked by code. A
  name Gemini misses would travel in the voice note. If you cannot accept that, send only the one-line complaint.
- **Sex is never read** from the ID, so `patient.sex` is always empty. Initials are still semi-identifying.
- **A server started before this change** (for example an old `run.py --serve`) lacks the hand-off routes: restart it.
- Everything clinical in the demo is illustrative. It is decision support, not a diagnosis.

## 7. Working agreements

- Commit and push only when asked. Real Google or Presage calls are made only when needed for the task, kept small,
  and reported.
- Every model name and tuning number lives in `inputs/.env`, never in code. Config errors must name the setting.
- Report what was and was not verified. Flag unverified claims rather than smoothing them over.
- Keep the page clean for end users: raw JSON, logs and replays stay in the collapsed developer panel.
