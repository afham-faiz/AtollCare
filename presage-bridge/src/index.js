// AtollCare Presage bridge. Three ways in, one SmartSpectra SDK:
//
// Live scan (a phone, the default): the phone streams JPEG frames over WebSocket while the patient is framed; Presage
//   answers with framing hints, HR, RR and the breathing wave within seconds. "mark" starts the measured window,
//   "stop" returns the whole sample trace as a summary, which the phone uploads with its clip. Nothing is posted here.
//   phone ──JPEG frames (wss, same origin /presage/ws)──► bridge ──sendFrame──► SDK ──► live metrics + summary
//
// Monitor (a laptop or tablet on a mount): the same stream, continuously; stable, fresh values go to the engine.
//   bridge ──every 5 s──► engine  POST /api/transfers/{id}/vitals  (numbers only; video never leaves)
//
// File (fallback when the phone couldn't stream): the engine converts the uploaded clip to MJPEG and posts it here.
//   engine ──POST /vitals/file (.avi bytes)──► bridge ──useFile, real-time playback──► SDK ──► whole sample trace
//   (Percy's presage-sidecar, merged in: real-time pace, because faster playback drops frames and loses the face)
//
// Env: PRESAGE_API_KEY (physiology.presagetech.com), ENGINE_URL (default http://localhost:8000), PORT (8787).
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";

import jpeg from "jpeg-js";
import { WebSocketServer } from "ws";

const PORT = Number(process.env.PORT ?? 8787);
const ENGINE_URL = (process.env.ENGINE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const API_KEY = process.env.PRESAGE_API_KEY ?? "";
const POST_INTERVAL_MS = 5000;
const FRESH_MS = 5000; // a value older than this (face gone, camera covered) is never posted as current
const HEARTBEAT_MS = 5000;
const RGBA_MAGIC = 0x41435046; // "ACPF": raw RGBA frame
const JPEG_MAGIC = 0x4143504a; // "ACPJ": JPEG frame (phones: ~30 KB instead of ~900 KB)
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

// One SDK session at a time — native SDK state is process-global. A scan (live or file) pauses a monitor session;
// the monitor's screen is told to resume when the scan is done.
let active = null;
let fileRunning = false;
const paused = new Set();

const last = (arr) => (Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null);

// Map Presage's own accuracy verdict (`stable`) onto the engine's 0.6 quality gate.
const toConfidence = (m) => {
  if (!m) return null;
  const c = Math.max(0, Math.min(1, (m.confidence ?? 0) / 100));
  return m.stable ? Math.max(0.6, c) : Math.min(0.59, c);
};

// One Presage sample for a trace: value, confidence 0–1 and Presage's own verdict.
const sample = (m) => (m && m.value != null ? { value: m.value, confidence: (m.confidence ?? 0) / 100, stable: !!m.stable } : null);

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

// Keep responses small: at most ~200 points per series.
function thin(series, max = 200) {
  if (series.length <= max) return series;
  const step = Math.ceil(series.length / max);
  return series.filter((_, i) => i % step === 0 || i === series.length - 1);
}

// A recording (live or file) as one result: the last values, Presage's hints and the whole trace. Same shape for both
// paths, so the engine summarises them the same way (median of stable samples; see engine rppg_extractor.py).
function summary(rec, extra = {}) {
  const pulse = last(rec.pulseSeries);
  const breathing = last(rec.breathingSeries);
  const confidences = [pulse, breathing].filter(Boolean).map((x) => x.confidence);
  return {
    mode: "sdk",
    heart_rate_bpm: pulse ? Math.round(pulse.value) : null,
    respiration_rate_bpm: breathing ? Math.round(breathing.value) : null,
    confidence: confidences.length ? Math.min(...confidences) : 0,
    issues: [...rec.issues],
    hints: [...rec.hints],
    diagnostics: {
      validation_counts: rec.validationCounts,
      pulse_series: thin(rec.pulseSeries),
      breathing_series: thin(rec.breathingSeries),
      ...extra,
    },
  };
}

function newRecording() {
  return { pulseSeries: [], breathingSeries: [], issues: new Set(), hints: new Set(), validationCounts: {}, firstTs: null };
}

function codeName(code) {
  const entry = Object.entries(sdkModule.ValidationCode).find(([, c]) => c === code);
  return entry ? entry[0] : `code_${code}`;
}

function record(rec, m, timestampUs) {
  if (rec.firstTs === null) rec.firstTs = timestampUs;
  const t_s = Math.round(((timestampUs - rec.firstTs) / 1e6) * 10) / 10;
  const p = sample(last(m.cardio?.pulseRate));
  const b = sample(last(m.breathing?.rate));
  if (p) rec.pulseSeries.push({ t_s, ...p });
  if (b) rec.breathingSeries.push({ t_s, ...b });
}

function noteValidation(rec, code, hint) {
  const name = codeName(code);
  rec.validationCounts[name] = (rec.validationCounts[name] || 0) + 1;
  if (code !== 0) {
    rec.issues.add(name);
    rec.hints.add(hint || HINTS[code] || name);
  }
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

// A scan finished: monitor screens it paused can start again.
function resumePaused() {
  if (active || fileRunning) return;
  for (const ws of paused) send(ws, { type: "status", state: "resume", message: "Presage is free again" });
  paused.clear();
}

async function makeRoom(kind) {
  if (!active) return;
  const victim = active;
  const pauseIt = kind === "scan" && victim.kind === "monitor";
  if (pauseIt) paused.add(victim.ws);
  send(victim.ws, {
    type: "status",
    state: pauseIt ? "paused" : "taken_over",
    message: pauseIt ? "A scan is using Presage — this screen resumes when it's done" : "Another screen took over the camera session",
  });
  await stopSession(victim);
}

async function startSession(ws, { transferId, kind }) {
  await makeRoom(kind);
  const { SmartSpectraSDK, FrameTransform, breathingMetrics, cardioMetrics } = sdkModule;
  const sdk = new SmartSpectraSDK({ apiKey: API_KEY, requestedMetrics: [...breathingMetrics, ...cardioMetrics], enableTelemetry: false });
  const session = {
    ws, sdk, kind, transferId, lastTs: 0, latest: {}, hint: null, frames: 0, postTimer: null, failed: false,
    rec: newRecording(), markedAt: Date.now(),
  };

  sdk.on("metrics", (buf, timestampUs) => {
    let m;
    try {
      m = decodeMetrics(buf);
    } catch {
      return;
    }
    record(session.rec, m, timestampUs);
    const pulse = last(m.cardio?.pulseRate);
    const rate = last(m.breathing?.rate);
    const hrv = last(m.cardio?.hrv);
    const trace = (m.breathing?.upperTrace ?? []).slice(-60).map((p) => p.value ?? 0);
    const at = Date.now();
    if (pulse?.value) session.latest.hr = { value: pulse.value, conf: toConfidence(pulse), stable: !!pulse.stable, at };
    if (rate?.value) session.latest.rr = { value: rate.value, conf: toConfidence(rate), stable: !!rate.stable, at };
    if (hrv?.rmssd) session.latest.hrv = { value: hrv.rmssd, conf: toConfidence(hrv), stable: !!hrv.stable, at };
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
    noteValidation(session.rec, code, hint);
    // the face left the frame (or the light went): whatever was measured before is no longer the patient now
    if (code !== 0) session.latest = {};
    send(ws, { type: "validation", code, ok: code === 0, hint: session.hint });
  });
  sdk.on("processingStatus", (status) => send(ws, { type: "processing", status }));
  sdk.on("error", (code, message, retryable) => {
    console.warn(`[bridge] SDK error ${code}: ${message}`);
    send(ws, { type: "error", code, message, retryable });
    if (!retryable && !session.failed) {
      // e.g. kAuthenticationFailed / kCreditExhausted: stop pushing frames; the screen says why
      session.failed = true;
      send(ws, { type: "status", state: "error", message });
    }
  });

  sdk.useCustomInput(FrameTransform.kNone);
  sdk.start();
  active = session;

  // Monitor sessions post the latest stable, fresh values to the engine; scans hand back one summary instead.
  if (kind === "monitor" && transferId) {
    session.postTimer = setInterval(async () => {
      const fresh = (x) => (x && Date.now() - x.at <= FRESH_MS ? x : null);
      const [hr, rr, hrv] = [fresh(session.latest.hr), fresh(session.latest.rr), fresh(session.latest.hrv)];
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
  }

  send(ws, { type: "status", state: "running", message: sdkMessage });
  console.log(`[bridge] ${kind} session started${transferId ? ` for transfer ${transferId}` : ""}`);
  return session;
}

function handleFrame(session, data) {
  if (session.failed || data.length < HEADER_BYTES) return;
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const magic = view.getUint32(0);
  const tsMs = view.getFloat64(8);
  const payload = data.subarray(HEADER_BYTES);
  let pixels;
  let width;
  let height;
  let format;
  let channels;
  if (magic === RGBA_MAGIC) {
    width = view.getUint16(4);
    height = view.getUint16(6);
    if (payload.length !== width * height * 4) return;
    pixels = payload;
    format = sdkModule.PixelFormat.kRGBA;
    channels = 4;
  } else if (magic === JPEG_MAGIC) {
    try {
      const img = jpeg.decode(payload, { useTArray: true, formatAsRGBA: false });
      ({ width, height } = img);
      pixels = img.data;
    } catch {
      return; // a torn frame: skip it
    }
    format = sdkModule.PixelFormat.kRGB;
    channels = 3;
  } else {
    return;
  }
  // timestamps must be strictly increasing microseconds (capture time on the phone, not arrival time here)
  let tsUs = Math.round(tsMs * 1000);
  if (tsUs <= session.lastTs) tsUs = session.lastTs + 1;
  session.lastTs = tsUs;
  try {
    session.sdk.sendFrame(pixels, width, height, width * channels, format, tsUs);
    session.frames += 1;
  } catch (err) {
    if (!err.retryable) session.failed = true;
    send(session.ws, { type: "error", code: err.code ?? -1, message: err.message, retryable: !!err.retryable });
  }
}

// ── file mode: recorded clips the phone couldn't stream ──────────────────────────────────────────────────────────
const FILE_TIMEOUT_MS = Number(process.env.PRESAGE_TIMEOUT_MS ?? 240_000);
const MAX_UPLOAD_BYTES = 400 * 1024 * 1024; // 60 s of high-quality MJPEG at 960 px is ~150 MB
let queue = Promise.resolve(); // one SDK at a time: clips wait their turn
let fileJobs = 0;

function exclusive(fn) {
  const run = queue.then(fn, fn);
  queue = run.catch(() => {});
  return run;
}

async function fileVitals(clipPath) {
  const { SmartSpectraSDK, ProcessingStatus, breathingMetrics, cardioMetrics } = sdkModule;
  const rec = newRecording();
  const sdk = new SmartSpectraSDK({ apiKey: API_KEY, requestedMetrics: [...breathingMetrics, ...cardioMetrics], enableTelemetry: false });
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
      sdk.on("validationStatus", (code, _ts, hint) => noteValidation(rec, code, hint));
      sdk.on("metrics", (buf, timestampUs) => {
        try {
          record(rec, decodeMetrics(buf), timestampUs);
        } catch {
          // a packet we can't read: skip it
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
  return summary(rec, { path: "file" });
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
      fileRunning = true;
      try {
        await makeRoom("scan");
        return await fileVitals(clip);
      } finally {
        fileRunning = false;
        resumePaused();
      }
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
  // also reachable as /presage/* through the web app's proxy (one HTTPS address for phones)
  const url = (req.url ?? "").replace(/^\/presage(?=\/)/, "");
  if (url === "/health") {
    return json(res, 200, {
      ok: true, sdk: sdkState, message: sdkMessage, session: active ? { kind: active.kind, transfer: active.transferId ?? null } : null,
      file_jobs: fileJobs,
    });
  }
  if (req.method === "POST" && url === "/vitals/file") {
    handleFile(req, res);
    return;
  }
  res.statusCode = 404;
  res.end();
});

const wss = new WebSocketServer({ noServer: true, maxPayload: 16 * 1024 * 1024 });
server.on("upgrade", (req, socket, head) => {
  const url = (req.url ?? "").replace(/^\/presage(?=\/)/, "").split("?")[0];
  if (url !== "/ws") {
    socket.destroy();
    return;
  }
  wss.handleUpgrade(req, socket, head, (ws) => wss.emit("connection", ws, req));
});

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
      const kind = msg.kind === "scan" ? "scan" : "monitor";
      if (fileRunning) {
        // a recorded clip is being measured: this screen starts as soon as it's done
        paused.add(ws);
        send(ws, { type: "status", state: "paused", message: "Presage is measuring a recorded scan — starting in a moment" });
        return;
      }
      try {
        session = await startSession(ws, { transferId: msg.transferId, kind });
      } catch (err) {
        send(ws, { type: "status", state: "error", message: `Could not start SmartSpectra: ${err.message}` });
      }
    }
    // scan: the measured window starts now (Presage was already giving framing hints while the shot was lined up)
    if (msg.type === "mark" && session) {
      session.rec = newRecording();
      session.markedAt = Date.now();
    }
    if (msg.type === "stop") {
      const ending = session;
      session = null;
      if (ending?.kind === "scan" && msg.summary) {
        const seconds = Math.round((Date.now() - ending.markedAt) / 100) / 10;
        send(ws, { type: "summary", result: summary(ending.rec, { path: "live", frames: ending.frames, seconds }) });
      }
      await stopSession(ending);
      resumePaused();
    }
  });
  ws.on("close", async () => {
    paused.delete(ws);
    const ending = session;
    session = null;
    await stopSession(ending);
    resumePaused();
  });
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
