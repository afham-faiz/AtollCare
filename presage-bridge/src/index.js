// AtollCare Presage bridge — runs next to the camera (the "edge device" in the vehicle).
//
//   browser (crew screen) ──RGBA frames over WebSocket──► bridge ──sendFrame──► Presage SmartSpectra SDK
//   browser ◄── live HR / RR / HRV / breathing trace / framing hints ── bridge
//   bridge ──every 5 s──► AtollCare engine  POST /api/transfers/{id}/vitals  (numbers only; video never leaves)
//
// Env: PRESAGE_API_KEY (physiology.presagetech.com), ENGINE_URL (default http://localhost:8000), PORT (8787).
import http from "node:http";

import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT ?? 8787);
const ENGINE_URL = (process.env.ENGINE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const API_KEY = process.env.PRESAGE_API_KEY ?? "";
const POST_INTERVAL_MS = 5000;
const HEARTBEAT_MS = 5000;
const FRAME_MAGIC = 0x41435046; // "ACPF"
const HEADER_BYTES = 16; // u32 magic, u16 width, u16 height, f64 capture time (ms)

// Human-readable framing hints for ValidationCode values (SDK hint strings are used when present).
const HINTS = {
  1: "No face found — point the camera at the patient",
  2: "More than one face in view",
  3: "Centre the face in the frame",
  4: "Adjust the distance to the patient",
  5: "Too dark — add light",
  6: "Too bright — reduce glare",
  7: "Chest not visible — show the upper chest",
  10: "Camera adjusting…",
  11: "Frame rate too low",
  12: "Too much movement — hold still",
  13: "Too close — move the camera back",
  14: "Too far — move the camera closer",
  15: "Face too high in frame",
  16: "Face too low in frame",
  17: "Patient should face the camera",
};

let sdkModule = null;
let decodeMetrics = null;
let sdkState = API_KEY ? "unavailable" : "no_api_key";
let sdkMessage = API_KEY ? "Loading SmartSpectra SDK…" : "Set PRESAGE_API_KEY to enable live measurement";

try {
  sdkModule = await import("@smartspectra/node-sdk");
  ({ decodeMetrics } = await import("@smartspectra/node-sdk/messages"));
  if (API_KEY) {
    sdkState = "ready";
    sdkMessage = `SmartSpectra ${sdkModule.SmartSpectraSDK.version}`;
  }
} catch (err) {
  sdkState = "unavailable";
  sdkMessage = `SmartSpectra SDK failed to load: ${err.message}`;
}

let active = null; // one SDK session at a time — native SDK state is process-global

const last = (arr) => (Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null);

// Map Presage's own accuracy verdict (`stable`) onto the engine's 0.6 quality gate.
const toConfidence = (m) => {
  if (!m) return null;
  const c = Math.max(0, Math.min(1, (m.confidence ?? 0) / 100));
  return m.stable ? Math.max(0.6, c) : Math.min(0.59, c);
};

async function postJson(path, body) {
  try {
    const res = await fetch(`${ENGINE_URL}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) console.warn(`[bridge] ${path} → ${res.status} ${await res.text()}`);
    return res.ok;
  } catch (err) {
    console.warn(`[bridge] engine unreachable (${err.message})`);
    return false;
  }
}

function send(ws, msg) {
  if (ws.readyState === ws.OPEN) ws.send(JSON.stringify(msg));
}

async function stopSession(session) {
  if (!session) return;
  clearInterval(session.postTimer);
  try {
    await session.sdk.stopAsync();
  } catch {
    // already stopped
  }
  try {
    await session.sdk.destroy();
  } catch {
    // already destroyed
  }
  if (active === session) active = null;
}

async function startSession(ws, transferId) {
  if (active) {
    send(active.ws, { type: "status", state: "taken_over", message: "Another screen took over the camera session" });
    await stopSession(active);
  }
  const { SmartSpectraSDK, FrameTransform, breathingMetrics, cardioMetrics } = sdkModule;
  const sdk = new SmartSpectraSDK({ apiKey: API_KEY, requestedMetrics: [...breathingMetrics, ...cardioMetrics] });
  const session = { ws, sdk, transferId, lastTs: 0, latest: {}, hint: null, frames: 0, postTimer: null, failed: false };

  sdk.on("metrics", (buf) => {
    let m;
    try {
      m = decodeMetrics(buf);
    } catch {
      return;
    }
    const pulse = last(m.cardio?.pulseRate);
    const rate = last(m.breathing?.rate);
    const hrv = last(m.cardio?.hrv);
    const trace = (m.breathing?.upperTrace ?? []).slice(-60).map((p) => p.value ?? 0);
    if (pulse?.value) session.latest.hr = { value: pulse.value, conf: toConfidence(pulse), stable: !!pulse.stable };
    if (rate?.value) session.latest.rr = { value: rate.value, conf: toConfidence(rate), stable: !!rate.stable };
    if (hrv?.rmssd) session.latest.hrv = { value: hrv.rmssd, conf: toConfidence(hrv), stable: !!hrv.stable };
    send(ws, {
      type: "metrics",
      hr: session.latest.hr ?? null,
      rr: session.latest.rr ?? null,
      hrv: session.latest.hrv ?? null,
      trace,
    });
  });
  sdk.on("validationStatus", (code, _ts, hint) => {
    session.hint = code === 0 ? null : hint || HINTS[code] || `Adjust camera (code ${code})`;
    send(ws, { type: "validation", code, ok: code === 0, hint: session.hint });
  });
  sdk.on("processingStatus", (status) => send(ws, { type: "processing", status }));
  sdk.on("error", (code, message, retryable) => {
    console.warn(`[bridge] SDK error ${code}: ${message}`);
    send(ws, { type: "error", code, message, retryable });
    if (!retryable && !session.failed) {
      // e.g. kAuthenticationFailed / kCreditExhausted: stop pushing frames; the crew screen falls back to simulated
      session.failed = true;
      send(ws, { type: "status", state: "error", message });
    }
  });

  sdk.useCustomInput(FrameTransform.kNone);
  sdk.start();
  active = session;

  // Throttled post of the latest stable values to the engine (Tiger Data hypertable via the API).
  session.postTimer = setInterval(async () => {
    const { hr, rr, hrv } = session.latest;
    const stable = [hr, rr, hrv].filter((x) => x?.stable);
    if (!stable.length) return;
    await postJson(`/api/transfers/${transferId}/vitals`, {
      source: "presage",
      heart_rate: hr?.stable ? Math.round(hr.value) : null,
      resp_rate: rr?.stable ? Math.round(rr.value) : null,
      hrv_rmssd: hrv?.stable ? Math.round(hrv.value * 10) / 10 : null,
      confidence: Math.min(...stable.map((x) => x.conf)),
      hint: session.hint,
    });
  }, POST_INTERVAL_MS);

  send(ws, { type: "status", state: "running", message: sdkMessage });
  console.log(`[bridge] session started for transfer ${transferId}`);
  return session;
}

function handleFrame(session, data) {
  if (session.failed || data.length < HEADER_BYTES) return;
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  if (view.getUint32(0) !== FRAME_MAGIC) return;
  const width = view.getUint16(4);
  const height = view.getUint16(6);
  const tsMs = view.getFloat64(8);
  const pixels = data.subarray(HEADER_BYTES);
  if (pixels.length !== width * height * 4) return;
  // timestamps must be strictly increasing microseconds
  let tsUs = Math.round(tsMs * 1000);
  if (tsUs <= session.lastTs) tsUs = session.lastTs + 1;
  session.lastTs = tsUs;
  try {
    session.sdk.sendFrame(pixels, width, height, width * 4, sdkModule.PixelFormat.kRGBA, tsUs);
    session.frames += 1;
  } catch (err) {
    if (!err.retryable) session.failed = true;
    send(session.ws, { type: "error", code: err.code ?? -1, message: err.message, retryable: !!err.retryable });
  }
}

const server = http.createServer((req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  if (req.url === "/health") {
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ ok: true, sdk: sdkState, message: sdkMessage, session: active?.transferId ?? null }));
    return;
  }
  res.statusCode = 404;
  res.end();
});

const wss = new WebSocketServer({ server, path: "/ws", maxPayload: 16 * 1024 * 1024 });

wss.on("connection", (ws) => {
  let session = null;
  send(ws, { type: "hello", sdk: sdkState, message: sdkMessage });
  ws.on("message", async (data, isBinary) => {
    if (isBinary) {
      if (session && active === session) handleFrame(session, data);
      return;
    }
    let msg;
    try {
      msg = JSON.parse(data.toString());
    } catch {
      return;
    }
    if (msg.type === "start") {
      if (sdkState !== "ready") {
        send(ws, { type: "status", state: sdkState, message: sdkMessage });
        return;
      }
      try {
        session = await startSession(ws, msg.transferId);
      } catch (err) {
        send(ws, { type: "status", state: "error", message: `Could not start SmartSpectra: ${err.message}` });
      }
    }
    if (msg.type === "stop") {
      await stopSession(session);
      session = null;
    }
  });
  ws.on("close", () => stopSession(session));
});

setInterval(() => {
  postJson("/api/presage/heartbeat", {
    sdk: sdkState,
    version: sdkModule?.SmartSpectraSDK?.version ?? null,
    clients: wss.clients.size,
    message: sdkMessage,
  });
}, HEARTBEAT_MS);

server.listen(PORT, () => {
  console.log(`[bridge] listening on ws://localhost:${PORT}/ws — SDK: ${sdkState} (${sdkMessage}) — engine: ${ENGINE_URL}`);
});
