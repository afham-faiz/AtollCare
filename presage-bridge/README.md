# Presage bridge

Runs the official Presage SmartSpectra Node SDK for every screen that measures, with three ways in:

- **Live scan (a phone):** the phone streams JPEG frames over a WebSocket while the patient is framed. Presage answers
  with framing hints, then HR, RR, the pulse and chest-movement waveforms, apnea and talking detection. When the phone
  stops, the bridge hands back the whole trace as one summary, which the phone uploads with its clip.
- **Monitor (a mounted laptop or tablet):** the same stream, continuously; every 5 s the bridge posts the latest
  stable, fresh values (under 5 s old) to the engine.
- **File (fallback):** the engine posts a clip the phone couldn't stream (MJPEG, 30 fps) to `POST /vitals/file`.

```
phone / laptop ──JPEG frames (wss://…/presage/ws)──► bridge ──sendFrame──► SmartSpectra SDK
phone / laptop ◄── hints · HR · RR · waveforms · summary ── bridge ──(monitor) vitals──► engine
engine ──POST /vitals/file (MJPEG)──► bridge ──useFile──► SmartSpectra SDK
```

One SDK session at a time (its native state is per process). A scan pauses a continuous monitor session and the
monitor's screen resumes by itself when the scan is done.

## Run

Requires Node 20+ (Windows x64, macOS Apple Silicon, or Linux x64/arm64 with glibc 2.35+).

```bash
npm install
```

```bash
node --env-file=../.env src/index.js
```

Get an API key at https://physiology.presagetech.com. Without a key the bridge still runs and reports `no_api_key`.

| Env | Default | |
|---|---|---|
| `PRESAGE_API_KEY` | — | Required for measurement |
| `ENGINE_URL` | `http://localhost:8000` | Engine base URL (monitor mode posts here) |
| `PORT` | `8787` | WebSocket at `/ws`, health at `/health`, clips at `/vitals/file`; all also answer under `/presage/…` |

Phones reach it through the web app (Next proxies `/presage/*` here), so one HTTPS address serves the app, the API and
Presage: see `scripts/phone_tunnel.sh`.

## Rehearse without a phone

```bash
node scripts/replay.mjs face.mp4 --ffmpeg /path/to/ffmpeg
```

Streams a video file through the live path exactly as a phone does (JPEG frames at the clip's own pace, with capture
timestamps) and prints Presage's summary. Use a recorded face to check the whole chain before a demo.

## Getting a good measurement

From Presage's model cards and its FDA clearance (K254169: spot checks, phone in a static mount, trained staff,
healthy adults 18–70):

- Prop the phone up or mount it. Breathing rate needs a camera that is **not handheld**.
- Keep the patient's face **and upper chest** in view, well lit, and not backlit.
- The patient should be still and not talking (the companion can talk off camera).
- 30 s window. Pulse is cleared for 50–150 bpm and breathing for 8–26 /min; screens flag readings outside that.
- "Stable" is Presage's own accuracy standard: ±3 bpm for pulse, ±1 breath/min for breathing.

## Protocol

Text messages:

- Client → bridge: `{"type":"start","kind":"scan"|"monitor","transferId":"…"}`, `{"type":"mark"}` (scan: the measured
  window starts now), `{"type":"stop","summary":true}` (scan: send the summary first).
- Bridge → client: `hello`, `status` (`running`, `paused`, `resume`, `taken_over`, `error`), `metrics`
  `{hr,rr,hrv:{value,conf,stable},trace:[…],pulse:[…],apnea}`, `validation` `{code,ok,hint}`, `summary` `{result}`,
  and `error`.

Binary frames: a 16-byte big-endian header — `u32` magic, `u16` width, `u16` height, `f64` capture time in ms — then
the payload. Magic `0x4143504a` ("ACPJ"): a JPEG (phones; the size comes from the JPEG). Magic `0x41435046`
("ACPF"): width × height × 4 RGBA bytes.

The summary (live or file) has the same shape: `heart_rate_bpm`, `respiration_rate_bpm`, `hints`, `issues` and
`diagnostics` with `pulse_series` / `breathing_series` (value, confidence, stable over time), `pulse_trace`,
`breathing_trace`, `apnea_s`, `talking_share`, `framing` (`{from_s,to_s,hint}`), `path` (`live` / `file`).
