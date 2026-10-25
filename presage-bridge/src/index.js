// AtollCare Presage bridge. Two ways in, one SmartSpectra SDK:
//
// Live (a laptop or tablet camera on a mount):
//   browser ──RGBA frames over WebSocket──► bridge ──sendFrame──► SDK ──► live HR / RR / HRV / trace / hints
//   bridge ──every 5 s──► engine  POST /api/transfers/{id}/vitals  (numbers only; video never leaves)
//
// File (a phone records ~60 s; the engine converts it to MJPEG and posts it here):
//   engine ──POST /vitals/file (.avi bytes)──► bridge ──useFile, real-time playback──► SDK ──► whole sample trace
//   (Percy's presage-sidecar, merged in: real-time pace, because faster playback drops frames and loses the face)
//
// Env: PRESAGE_API_KEY (physiology.presagetech.com), ENGINE_URL (default http://localhost:8000), PORT (8787).
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

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

// ── file mode: recorded clips from phones ─────────────────────────────────────
const FILE_TIMEOUT_MS = Number(process.env.PRESAGE_TIMEOUT_MS ?? 240_000);
const MAX_UPLOAD_BYTES = 400 * 1024 * 1024; // 60 s of high-quality MJPEG at 960 px is ~150 MB
let queue = Promise.resolve(); // one SDK at a time: clips wait their turn
let fileJobs = 0;

function exclusive(fn) {
  const run = queue.then(fn, fn);
  queue = run.catch(() => {});
  return run;
}

// Keep responses small: at most ~200 points per series.
function thin(series, max = 200) {
  if (series.length <= max) return series;
  const step = Math.ceil(series.length / max);
  return series.filter((_, i) => i % step === 0 || i === series.length - 1);
}

async function fileVitals(clipPath) {
  const { SmartSpectraSDK, ValidationCode, ProcessingStatus, breathingMetrics, cardioMetrics } = sdkModule;
  const codeNames = Object.fromEntries(Object.entries(ValidationCode).map(([name, code]) => [code, name]));
  const issues = new Set();
  const hints = new Set();
  const validationCounts = {};
  const pulseSeries = [];
  const breathingSeries = [];
  let firstTs = null;
  let pulse = null;
  let breathing = null;

  const sdk = new SmartSpectraSDK({ apiKey: API_KEY, requestedMetrics: [...breathingMetrics, ...cardioMetrics], enableTelemetry: false });
  const sample = (m) => (m && m.value != null ? { value: m.value, confidence: (m.confidence ?? 0) / 100, stable: !!m.stable } : null);
  try {
    const done = new Promise((resolve, reject) => {
      let sawRunning = false;
      const timer = setTimeout(() => reject(new Error("SDK timed out")), FILE_TIMEOUT_MS);
      const finish = (fn, arg) => {
        clearTimeout(timer);
        fn(arg);
      };
      sdk.on("processingStatus", (status) => {
        if (status === ProcessingStatus.kRunning) sawRunning = true;
        if (status === ProcessingStatus.kError) finish(reject, new Error("SDK processing error"));
        if (status === ProcessingStatus.kIdle && sawRunning) finish(resolve);
      });
      sdk.on("error", (code, message) => finish(reject, new Error("SDK error " + code + ": " + message)));
      sdk.on("validationStatus", (code, _ts, hint) => {
        const name = codeNames[code] || "code_" + code;
        validationCounts[name] = (validationCounts[name] || 0) + 1;
        if (code !== ValidationCode.kOk) {
          issues.add(name);
          hints.add(hint || HINTS[code] || name);
        }
      });
      sdk.on("metrics", (buf, timestampUs) => {
        let m;
        try {
          m = decodeMetrics(buf);
        } catch {
          return;
        }
        if (firstTs === null) firstTs = timestampUs;
        const t_s = Math.round(((timestampUs - firstTs) / 1e6) * 10) / 10;
        const p = sample(last(m.cardio?.pulseRate));
        const b = sample(last(m.breathing?.rate));
        if (p) {
          pulse = p;
          pulseSeries.push({ t_s, ...p });
        }
        if (b) {
          breathing = b;
          breathingSeries.push({ t_s, ...b });
        }
      });
    });
    done.catch(() => {}); // start() can emit synchronously; mark `done` handled before it can reject
    sdk.useFile(clipPath, { interframeDelayMs: 33 });
    sdk.start();
    await done;
  } finally {
    await sdk.destroy().catch(() => {});
  }

  const confidences = [pulse, breathing].filter(Boolean).map((x) => x.confidence);
  return {
    mode: "sdk",
    heart_rate_bpm: pulse ? Math.round(pulse.value) : null,
    respiration_rate_bpm: breathing ? Math.round(breathing.value) : null,
    confidence: confidences.length ? Math.min(...confidences) : 0,
    issues: [...issues],
    hints: [...hints],
    diagnostics: { validation_counts: validationCounts, pulse_series: thin(pulseSeries), breathing_series: thin(breathingSeries) },
  };
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > MAX_UPLOAD_BYTES) {
        reject(new Error("payload too large"));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function json(res, status, body) {
  res.writeHead(status, { "Content-Type": "application/json" });
  res.end(JSON.stringify(body));
}

async function handleFile(req, res) {
  if (sdkState !== "ready") return json(res, 503, { error: sdkMessage, sdk: sdkState });
  const clip = path.join(os.tmpdir(), "presage-" + crypto.randomUUID() + ".avi");
  try {
    const body = await readBody(req);
    if (!body.length) return json(res, 400, { error: "empty video body" });
    fs.writeFileSync(clip, body);
    fileJobs += 1;
    const result = await exclusive(async () => {
      if (active) {
        send(active.ws, { type: "status", state: "taken_over", message: "A recorded scan is using Presage" });
        await stopSession(active);
      }
      return fileVitals(clip);
    });
    console.log("[bridge] clip measured: HR " + (result.heart_rate_bpm ?? "-") + " RR " + (result.respiration_rate_bpm ?? "-"));
    return json(res, 200, result);
  } catch (err) {
    return json(res, 500, { error: String(err.message || err) });
  } finally {
    fileJobs = Math.max(0, fileJobs - 1);
    fs.rm(clip, { force: true }, () => {});
  }
}

const server = http.createServer((req, res) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  if (req.url === "/health") {
    return json(res, 200, { ok: true, sdk: sdkState, message: sdkMessage, session: active?.transferId ?? null, file_jobs: fileJobs });
  }
  if (req.method === "POST" && req.url === "/vitals/file") {
    handleFile(req, res);
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
