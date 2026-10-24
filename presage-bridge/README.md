# Presage bridge

Edge service that runs **next to the camera** (the laptop or tablet mounted in the vehicle). The crew screen streams
camera frames to it over a local WebSocket; it feeds them to the official Presage SmartSpectra Node SDK and sends live
heart rate, breathing rate, HRV, the breathing waveform and framing hints back to the screen. Every 5 s it posts the
latest *stable* values to the AtollCare engine. Video never leaves the device.

```
browser ──RGBA frames──► bridge ──sendFrame──► SmartSpectra SDK
browser ◄── HR / RR / HRV / trace / hints ── bridge ──vitals──► engine /api/transfers/{id}/vitals
```

## Run

Requires Node 20+ (Windows x64, macOS Apple Silicon, or Linux x64/arm64 with glibc 2.35+).

```bash
npm install
```

```bash
PRESAGE_API_KEY=... ENGINE_URL=http://localhost:8000 npm start
```

Get an API key at https://physiology.presagetech.com. Without a key the bridge still runs and reports
`no_api_key`; the crew screen then switches to clearly labelled **simulated** vitals.

| Env | Default | |
|---|---|---|
| `PRESAGE_API_KEY` | — | Required for live measurement |
| `ENGINE_URL` | `http://localhost:8000` | Engine base URL (use the public HTTPS URL when the engine is on Vultr) |
| `PORT` | `8787` | WebSocket at `ws://localhost:8787/ws`, health at `/health` |

## Getting a good measurement

Taken from Presage's model card:

- Mount the camera. Breathing rate needs a camera that is **not handheld**.
- Keep the patient's face **and upper chest** in view, well lit, and not backlit.
- The patient should be still and not talking during the measurement.
- Breathing rate settles after 30 s. Pulse is validated for 40–110 BPM, and the crew screen flags readings outside
  that range.
- Dark or tightly striped clothing degrades breathing measurement.

## Protocol

Text messages:

- Client → bridge: `{"type":"start","transferId":"…"}` and `{"type":"stop"}`.
- Bridge → client: `hello`, `status`, `metrics` `{hr,rr,hrv:{value,conf,stable},trace:[…]}`,
  `validation` `{code,ok,hint}`, and `error`.

Binary frames: a 16-byte header — `u32` magic `0x41435046`, `u16` width, `u16` height, `f64` capture time in ms
(big-endian) — followed by width × height × 4 RGBA bytes.
