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
node scripts/replay.mjs fixtures/face.mp4 [--seconds 30] [--url wss://….trycloudflare.com/presage/ws] [--ffmpeg /path/to/ffmpeg]
```

Streams a video file through the live path exactly as a phone does (JPEG frames at the clip's own pace, with capture
timestamps), prints Presage's summary and the numbers the phone would show, and exits 1 without a stable heart rate.

Before a demo, run the whole chain instead: `node scripts/predemo_check.mjs` from the repo root checks the services,
the public link and Gemini, streams `fixtures/face.mp4` through the public link, uploads it and waits for the scan.

`fixtures/` is kept out of git (a face on video). Put a 40–45 s clip there as `face.mp4`: one still person, face high in
the frame with the chest below it, lit from the front, ideally talking for part of it so the spoken account is
exercised too. We used a public-domain video address with black padding added below the picture; without the room
below the face, Presage reported `kChestNotVisible` on every frame and measured nothing.

## Getting a good measurement

From Presage's model cards and its FDA clearance (K254169: spot checks, phone in a static mount, trained staff,
healthy adults 18–70):

- Prop the phone up or mount it. Breathing rate needs a camera that is **not handheld**.
- Keep the patient's face **and chest down to the belly** in view, well lit, and not backlit. Presage measures
  nothing while it reports `kChestNotVisible`, which a face close-up always triggers.
- The patient should be still and not talking (the companion can talk off camera).
- 30 s window. Pulse is cleared for 50–150 bpm and breathing for 8–26 /min; screens flag readings outside that.
- "Stable" is Presage's own accuracy standard: ±3 bpm for pulse, ±1 breath/min for breathing.

## Protocol

Text messages:

- Client → bridge: `{"type":"start","kind":"scan"|"monitor","transferId":"…"}`, `{"type":"mark"}` (scan: the measured
  window starts now), `{"type":"stop","summary":true}` (scan: send the summary first).
- Bridge → client: `hello`, `status` (`running`, `restarting`, `paused`, `resume`, `taken_over`, `error`), `metrics`
  `{hr,rr,hrv:{value,conf,stable},trace:[…],pulse:[…],apnea}`, `validation` `{code,ok,hint}`, `summary` `{result}`,
  and `error`.

Sessions start and stop one at a time (the SDK's native state is process-global; a replacement must wait for the
old session's `destroy()`). A session the SDK gives up on (`kInvalidState`, `kProcessingFailed`, or any error it
calls not retryable) is rebuilt up to twice per `start`: the screen gets `restarting`, then `running`, and a scan
keeps its recording across the restart. The web app also reconnects by itself after a dropped connection or an
`error` (four times in a row at most), and waits 300 ms before connecting so a camera that turns off and on again
doesn't open a second session.

Binary frames: a 16-byte big-endian header — `u32` magic, `u16` width, `u16` height, `f64` capture time in ms — then
the payload. Magic `0x4143504a` ("ACPJ"): a JPEG (phones; the size comes from the JPEG). Magic `0x41435046`
("ACPF"): width × height × 4 RGBA bytes.

The summary (live or file) has the same shape: `heart_rate_bpm`, `respiration_rate_bpm`, `hints`, `issues` and
`diagnostics` with `pulse_series` / `breathing_series` (value, confidence, stable over time), `pulse_trace`,
`breathing_trace`, `apnea_s`, `talking_share`, `framing` (`{from_s,to_s,hint}`), `path` (`live` / `file`).
