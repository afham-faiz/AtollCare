# AtollCare: Part 1, pre-arrival

AtollCare is an AI-assisted emergency referral flow from remote communities to the hospital that can treat the patient. It has three parts (pre-arrival, referral, transport). **This branch (`user-branch`) is Part 1 only.** The wider idea, Parts 2 and 3 and the shared Case Record are described on `main`.

---

## Part 1: Pre-arrival at the local health centre
Goal: by the time the patient reaches the health centre, staff already know who the patient is, what is wrong, and what to prepare.

| Input | Action | Output |
|---|---|---|
| Video of the patient | Scan the face | Vital cues and supplementary observations |
| Voice of the person accompanying the patient | They describe what they see and what they need | Instructions and feedback to the companion, plus supplementary observations |
| Image of the patient's ID | Scan the details | Prompts that help the local health centre get help ready |

**Hands off:** a **pre-arrival packet** (identity, early vital cues, observations, companion's account) sent to the health centre before the patient walks in. The ID and slot check is done in advance.

### Running the Part 1 prototype

**What exists so far**

| Built | Not built yet |
|---|---|
| Face video → heart rate and breathing rate, with a quality score ([Presage SmartSpectra](https://smartspectra.presagetech.com)) | Speech slurring (needs the audio itself, not only the text) |
| Companion's voice → text, from the microphone or an uploaded audio file (Gemini 3.8 Flash) | Turning the transcript into observations and instructions for the companion |
| ID photo → name, ID number and age (Gemini vision). Unclear fields stay blank and the card is flagged "needs review" | Insurance check (an ID card does not say) |
| **Visual signs:** frames of the video are checked for visible signs (Gemini). Every sign in a fixed catalogue is checked and answered separately; a voice account, if there is one, only marks which signs it mentioned (with a quote that must appear in it). Every "seen" cites frames you can look at, and anything the account claims but the video does not show is listed | A clinically validated sign list (the catalogue in `src/data/cue_catalogue.json` is a demo assumption) |
| Patient video can be **uploaded or recorded with the camera in the browser**. A recording stays in the browser, and nothing goes to Google or Presage until you press Analyse | |
| **Hand-off to the crew app:** gathers the salient items (an initials label, age, a one-line complaint, Presage readings each with its own confidence, short notes), withholds the name, ID number and date of birth, shows a preview, and creates the transfer in the teammate's engine on an explicit click. Checked against their real engine | The crew app cannot yet label an AI video impression, so consciousness is not sent by default |
| **Phone as the capture device:** a phone page (`/phone`) records the ID photo, spoken account and face video and sends them to the laptop through a Cloudflare tunnel, protected by a secret key. The laptop does all the analysis | Running the analysis on the phone itself (native app) |
| A demo web page with four boxes (video, voice, ID, send) and a collapsed developer panel holding raw results, logs and replays | A final recommendation that combines all of the above (urgency level, what to prepare, what to tell the family) |

**What you need**

| Need | Notes |
|---|---|
| Python 3.13 | What it was built and tested on |
| Node.js 20 or later | Presage's SDK only exists for Node. It can live inside your virtual environment (see step 3) |
| A Presage API key | Free, from [physiology.presagetech.com](https://physiology.presagetech.com) |
| A Gemini API key | An AI Studio key, or a Google Cloud / Agent Platform key. Optional: without one the voice part runs in mock mode |
| A browser and a microphone | For the demo page |
| `cloudflared` | Only for using a phone. Install steps are in the phone section below |

Presage's SDK supports Windows x64, Linux x64 and ARM64 (glibc 2.35 or newer) and Apple Silicon Macs.

**Do not share the `.venv` folder.** It holds machine-specific paths and binaries, is several hundred MB, and is git-ignored. Everyone builds their own from [requirements.txt](requirements.txt). Likewise, never commit `inputs/.env`, which holds your keys.

**Setup (Windows PowerShell; on Mac/Linux use `source .venv/bin/activate`)**

```powershell
# 1. Python environment and packages
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Your keys: copy the template, then open inputs\.env and fill it in
mkdir inputs
copy env.example inputs\.env

# 3. Node.js inside the same environment (skip if you installed Node 20+ yourself)
nodeenv -p -n 24.11.0

# 4. The Presage SDK
cd presage-sidecar
npm install
cd ..
```

If `nodeenv` fails on Windows, install Node 24 LTS from [nodejs.org](https://nodejs.org) instead. Re-run the activate line in each new terminal.

**What goes in `inputs/.env`** (everything is configured here and nowhere in the code; restart after editing)

| Line | Meaning |
|---|---|
| `PRESAGE_API_KEY` | Your Presage key. `PRESAGE_MODE=mock` gives fake numbers with no key |
| `GEMINI_API_KEY` | Your Gemini key. Leave blank for mock voice |
| `GEMINI_USE_ENTERPRISE` | **Which kind of Gemini key you have.** `false` for a Google AI Studio key (starts with `AIza`), `true` for a Google Cloud / Gemini Agent Platform (Vertex AI) key. Teammates with different keys each set their own. An enterprise key's API restrictions must allow the Vertex AI / Agent Platform API, otherwise Google answers `API_KEY_SERVICE_BLOCKED` |
| `GEMINI_STT_MODEL` | Speech model, currently `gemini-3.8-flash`. A model with `live` in its name streams as you speak, but Google refuses it for express-mode API keys at the moment |
| `GEMINI_STT_FALLBACK_MODEL` | Optional backup model if the main one cannot start |
| `GEMINI_ID_MODEL` | Vision model that reads ID photos, currently `gemini-3.8-flash` |
| `GEMINI_CUE_PLANNER_MODEL`, `GEMINI_VQA_MODEL` | Models that choose the cues from the transcript, and inspect the video for them. Currently `gemini-3.8-flash` for both |
| `VQA_FRAME_INTERVAL_S`, `VQA_MAX_FRAMES` | One frame every this many seconds, and the most frames sent in total |
| `VIDEO_RECORD_MAX_S` | The longest camera recording, in seconds. Presage needs about 45 to 60 for a reliable breathing rate |
| `GEMINI_TIMEOUT_S`, `GEMINI_RETRY_ATTEMPTS` | Give up on a Google request that does not answer within this many seconds, and the number of tries. Without this, a stalled request would freeze the page forever |
| `ENGINE_URL`, `ENGINE_WEB_URL`, `ENGINE_TIMEOUT_S` | The teammate's crew-app engine (default `http://127.0.0.1:8010`), their web app for the "open on the crew screen" link, and how long to wait for it |
| `HANDSHAKE_PATIENT_LABEL` | `initials` (for example "D. M.") or `none`. Real names and ID numbers are never sent either way |
| `GEMINI_SUMMARY_MODEL` | Model that condenses the voice account into their one-line complaint and removes names and ID numbers from the full account |
| `HANDSHAKE_SEND_CONSCIOUSNESS`, `HANDSHAKE_CONSCIOUSNESS_MIN_CONFIDENCE` | Whether "alert and responsive" seen on video is sent as consciousness A, and how confident it must be. Off by default: their app would show it as a crew entry |
| `VQA_MODE` | `one_pass`: a single request with the frames, the voice account and every sign, answered one sign at a time. `two_step`: one request reads only the account and picks signs, a second sees only the frames, so it never sees the account |
| `GEMINI_CHAT_MODEL`, `TRANSCRIBE_LANGUAGE`, `STT_*` | Chat model, language, and timing settings |
| `ACCESS_TOKEN` | The secret key a phone needs to use the page through the tunnel. `python run.py --tunnel` creates one for you. Blank means tunnel traffic is refused |
| `SAVE_RECORDINGS` | `true` keeps every voice, upload and video trial in `recordings/` for replay |

**Run**

```powershell
python run.py --serve          # demo page at http://127.0.0.1:8000 (on Windows you can double-click start.bat)
python run.py --tunnel         # the same, plus a public link and QR code for a phone (on Windows, double-click start-phone.bat)
python run.py clip.mp4         # analyse one video from the command line
python run.py --mock           # try everything with no keys
python transcribe_file.py note.m4a   # transcribe an audio file
python scan_id.py card.jpg     # read the name and ID number from a photo of an ID
python visual_cues.py clip.mp4 --latest   # look for the signs the latest transcript suggests
python -m pytest               # tests (no keys needed, nothing is sent to Google)
```

The page only works while that command is running. `run.py` starts the Presage sidecar for you.

**Using the page.** Box 1 takes the patient video, either a file or a camera recording (video only, no sound, stopping by itself after `VIDEO_RECORD_MAX_S`). The browser only allows the camera and microphone on `localhost` or an HTTPS address, so a phone cannot use this page through the laptop's IP address; use the tunnel described below instead. Tick or untick *Also measure heart rate and breathing rate* to run Presage or skip it, and the visual signs are always checked. Box 2 takes the voice account, either recorded fresh or from a file you already have, and that account steers which signs are looked for in box 1's video. Box 3 reads the ID. Each box works alone. Raw results, logs and replays live in the collapsed *Developer details* panel at the bottom.

**Filming tips.** Presage needs 45 to 60 seconds with the phone propped still, the patient quiet and facing the camera, the face and upper chest in frame, and steady light on the face. Talking invalidates the breathing rate. It plays the video in real time, so a one-minute clip takes one to two minutes to analyse. Phone videos are shrunk automatically before analysis.

**Hand-off to the crew app (box 4).** *Preview* builds the packet from whatever boxes 1 to 3 produced, and shows what will be sent, what is held back on purpose, and what is missing. Pick From, To and Transport (read from their engine), then *Start transfer and send*. Four things to know:
- **Sending starts that transfer's journey clock** in their app, so do it when the crew actually leaves. The transfer arrives in their `preparing` state and the crew send the handoff themselves.
- **Names and ID numbers never cross.** The label is initials, the ID note only describes the card, and the spoken account is redacted by Gemini (and any run of 4 or more digits is masked). If the account cannot be checked, only the one-line summary goes.
- **Only real Presage readings are sent as vitals,** each with its own confidence. Mock or unavailable readings are never passed on. Monitoring is set to `presage` (or `off`) so their engine does not invent simulated vitals.
- **Their engine and this page must run on different ports.** This page uses 8000, so run their engine on 8010 (`ENGINE_URL`). To run it locally, run `python run_crew_engine.py` in a second terminal (run `git fetch origin` first). The first run copies their `engine/` folder from `origin/main`, builds its own environment and takes about a minute; after that it starts in seconds, with mock adapters and nothing saved. If the page says "server out of date", the server behind it was started before the hand-off existed: close it and start it again.

**Capturing on a phone.** See [Using a phone](#using-a-phone-as-the-capture-device) below.

**Where results go.** `logs/results.json`, `logs/transcripts.json`, `logs/id_scans.json`, `logs/handshakes.json` and `recordings/` hold your trials. They contain faces, voices and ID details, so they are git-ignored. Do not share them, and test with specimen or fake ID cards, not real ones. Photos you scan, and frames from videos you check for visual cues, are sent to Google's Gemini service using your key.

---

## Using a phone as the capture device

The laptop runs everything (Presage, Gemini, the logs). The phone is only a camera, microphone and screen. A free [Cloudflare quick tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/do-more-with-tunnels/trycloudflare/) gives the laptop a temporary public `https://` address, so the phone does not have to be on the same network. This also works on campus Wi-Fi such as eduroam, because only outbound HTTPS from the laptop is needed.

```
phone  --https-->  Cloudflare  <--outbound--  cloudflared (laptop)  -->  this app on 127.0.0.1:8000
```

Why a tunnel and not just the laptop's IP address: phone browsers only allow the camera and microphone on HTTPS (or `localhost`), and many networks stop devices talking to each other.

### 1. Install cloudflared (once)

On Windows, from PowerShell or Command Prompt:

```powershell
winget install Cloudflare.cloudflared
```

Close the terminal and open a new one, then check it worked:

```powershell
cloudflared --version
```

On macOS use `brew install cloudflared`. On Linux, see [Cloudflare's download page](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/). `cloudflared` is a program, not a Python package, so it is installed on the computer and not into `.venv`. No Cloudflare account is needed for a quick tunnel.

The Python side (the `segno` package that draws the QR code) is already in `requirements.txt`.

### 2. Start it

Windows: double-click **`start-phone.bat`**. Any system:

```powershell
python run.py --tunnel
```

This starts the app, opens the tunnel, and prints a link and a QR code. It also saves the QR code as `inputs/phone-link.png`. The first run creates an `ACCESS_TOKEN` line in `inputs/.env`. The laptop's browser opens at the same public address with the key already in it.

### 3. Open it on the phone

Scan the QR code with the phone camera. The page `/phone` has three steps:

1. **Photo of an ID** (optional).
2. **Spoken account** (optional). It is turned into text. Correct it if needed.
3. **Face video.** Prop the phone up, face the light, keep the face and upper chest in view, and stay still. The result (heart rate, breathing rate, signs seen) appears on the phone when the analysis finishes.

Everything is saved on the laptop in `logs/` and `recordings/`.

### 4. Send it to the crew app

On the laptop page, box 4, press **Use the latest saved results (for example from the phone)**. It loads the newest video check, its vitals and the newest ID scan, and says which files it used. Check they are the right ones, then press **Preview what will be sent**, and send as described under *Hand-off to the crew app*.

### Things to know

- **Keep the laptop awake and online** while the phone is in use. If it sleeps or loses the connection, the phone stops working.
- **The address changes every run.** After a restart, scan the new QR code. Old links and old browser tabs stop working. (A fixed address needs a Cloudflare account with your own domain, or a service such as ngrok.)
- **The link is a password.** It contains the secret key. Anyone who has it can use the page and download `recordings/` (faces, voices, ID photos). Do not post it, and stop the app when you are done. Requests through the tunnel are refused without the key. The laptop's own `127.0.0.1` address needs no key.
- **Long analyses are fine.** A tunnel cuts any single request off after about 100 seconds, so the phone starts the analysis as a background job and checks back every few seconds. Jobs are kept in memory, so restarting the app during an analysis loses it.
- **A phone is shakier than a laptop webcam,** so Presage readings are often poor at first. Prop it on a stand.
- **Camera or microphone blocked on the phone:** the page must be opened from the `https://` link, and Chrome on Android must be allowed to use them.
- **"cloudflared is not installed"** or `cloudflared did not give a public address`: check step 1, and that the network allows outbound HTTPS.
- **404 on "Use the latest saved results":** the app was started before that feature existed. Close it and start it again.

---

## Status

- [x] Face scan: Presage heart and breathing rate (upload, laptop camera or phone)
- [x] Voice account (record or file), ID scan, visual signs checked by Gemini
- [x] Phone capture over a Cloudflare tunnel with a secret key
- [x] Hand-off packet to the crew app, with a preview
- [ ] The pre-arrival summary that turns those outputs into an urgency level and an action list
- [ ] Speech slurring (needs the audio itself), signs that depend on movement, a clinically validated sign list
