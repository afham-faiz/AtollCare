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
  7: "Chest not visible — move back so the chest shows, down to the belly",
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
let sessionCount = 0;

// Every session change (start, stop, a recorded clip) runs one at a time. The SDK's own rule: await destroy() before
// building a replacement, since native state is process-global. A screen whose camera restarts opens a new socket
// while the old one is still closing; letting that teardown overlap the new start left the SDK in kInvalidState and
// the next session failing with kProcessingFailed (25 October: an Android phone and the crew laptop).
let lifecycle = Promise.resolve();
function serial(fn) {
  const run = lifecycle.then(fn, fn);
  lifecycle = run.catch(() => {});
  return run;
}
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const stamp = () => new Date().toISOString().slice(11, 19);
const FATAL_ERRORS = new Set([2, 3, 4]); // authentication, configuration, credits: a new session won't help
const DEAD_ERRORS = new Set([1, 8]); // kInvalidState, kProcessingFailed: the session has stopped measuring
const MAX_RESTARTS = 2; // per start from the screen
const RESTART_DELAY_MS = 750;
const TEARDOWN_MS = 8000; // a stop or destroy that hangs must not hold every later session up

// resolves when `promise` settles or after `ms`, whichever comes first; true if it settled
function within(promise, ms) {
  let timer;
  return Promise.race([
    promise.then(() => true, () => true),
    new Promise((resolve) => (timer = setTimeout(() => resolve(false), ms))),
  ]).finally(() => clearTimeout(timer));
}

const last = (arr) => (Array.isArray(arr) && arr.length ? arr[arr.length - 1] : null);
const num = (x) => (typeof x === "number" ? x : x && typeof x.toNumber === "function" ? x.toNumber() : Number(x));

// Breathing (with apnea), cardio (with the pulse waveform) and talking detection — talking is why a breathing rate
// can be off, so the report says how much of the scan the patient spent talking.
function requestedMetrics() {
  const { breathingMetrics, cardioMetrics, MetricType } = sdkModule;
  return [...breathingMetrics, ...cardioMetrics, MetricType.TALKING];
}

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
  closeFraming(rec);
  const trace = (points, max) => {
    const t0 = points[0]?.t ?? 0;
    return thin(points, max).map((p) => ({ t_s: Math.round((p.t - t0) / 1e4) / 100, v: Math.round(p.v * 1e4) / 1e4 }));
  };
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
      pulse_trace: trace(rec.pulseTrace, 600), // arterial pressure waveform (uncalibrated): the pulse itself
      breathing_trace: trace(rec.breathTrace, 300), // chest movement
      apnea_s: rec.apnea, // seconds into the scan where Presage detected breathing stop (stable detections only)
      talking_share: rec.faceSamples ? Math.round((rec.talking / rec.faceSamples) * 100) / 100 : null,
      framing: rec.framing, // [{from_s, to_s, hint}]: when the shot wasn't usable, and why
      ...extra,
    },
  };
}

function newRecording() {
  return {
    pulseSeries: [], breathingSeries: [], issues: new Set(), hints: new Set(), validationCounts: {}, firstTs: null,
    pulseTrace: [], breathTrace: [], lastPulseTs: -1, lastBreathTs: -1, apnea: [], inApnea: false, talking: 0,
    faceSamples: 0, framing: [], openFraming: null, startedAt: Date.now(),
  };
}

const sinceStart = (rec) => Math.round((Date.now() - rec.startedAt) / 100) / 10;

// framing problems as intervals of the recording (wall clock: the phone streams, and files play back, in real time)
function trackFraming(rec, code, hint) {
  const open = rec.openFraming;
  if (open && (code === 0 || open.code !== code)) closeFraming(rec);
  if (code !== 0 && !rec.openFraming) rec.openFraming = { code, hint, from_s: sinceStart(rec) };
}

function closeFraming(rec) {
  const open = rec.openFraming;
  if (!open) return;
  rec.openFraming = null;
  const to_s = sinceStart(rec);
  if (to_s - open.from_s >= 0.5) rec.framing.push({ from_s: open.from_s, to_s, hint: open.hint });
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
  // waveforms arrive as overlapping windows: keep each point once, in order
  for (const pt of m.cardio?.arterialPressureTrace ?? []) {
    const ts = num(pt.timestamp);
    if (pt.value != null && ts > rec.lastPulseTs) {
      rec.pulseTrace.push({ t: ts, v: pt.value });
      rec.lastPulseTs = ts;
    }
  }
  for (const pt of m.breathing?.upperTrace ?? []) {
    const ts = num(pt.timestamp);
    if (pt.value != null && ts > rec.lastBreathTs) {
      rec.breathTrace.push({ t: ts, v: pt.value });
      rec.lastBreathTs = ts;
    }
  }
  const apnea = last(m.breathing?.apnea);
  const stopped = !!(apnea?.detected && apnea?.stable);
  if (stopped && !rec.inApnea) rec.apnea.push(sinceStart(rec));
  rec.inApnea = stopped;
  for (const s of m.face?.talking ?? []) {
    rec.faceSamples += 1;
    if (s.detected) rec.talking += 1;
  }
}

function noteValidation(rec, code, hint) {
  const name = codeName(code);
  rec.validationCounts[name] = (rec.validationCounts[name] || 0) + 1;
  trackFraming(rec, code, hint || HINTS[code] || name);
  if (code !== 0) {
    rec.issues.add(name);
    rec.hints.add(hint || HINTS[code] || name);
  }
}

/** Tear a session down; idempotent. Only with the lifecycle held (inside `serial`). */
function endLocked(session) {
  if (!session) return Promise.resolve();
  session.ending ??= (async () => {
    clearInterval(session.postTimer);
    if (active === session) active = null;
    // errors here mean already stopped or destroyed
    const stopped = await within(Promise.resolve().then(() => session.sdk.stopAsync()), TEARDOWN_MS);
    const destroyed = await within(Promise.resolve().then(() => session.sdk.destroy()), TEARDOWN_MS);
    const hung = !stopped || !destroyed ? ` (gave up waiting for ${!stopped ? "stop" : "destroy"})` : "";
    console.log(`[bridge] ${stamp()} ${session.kind} session ${session.id} stopped${hung}`);
  })();
  return session.ending;
}

// A scan finished: monitor screens it paused can start again.
function resumePaused() {
  if (active || fileRunning || fileJobs) return;
  for (const ws of paused) send(ws, { type: "status", state: "resume", message: "Presage is free again" });
  paused.clear();
}

// Lifecycle held: the session using Presage gives way. A monitor is paused for a scan; anything else is taken over.
async function makeRoom(kind) {
  const victim = active;
  if (!victim) return;
  const pauseIt = kind === "scan" && victim.kind === "monitor";
  if (pauseIt) paused.add(victim.conn.ws);
  send(victim.conn.ws, {
    type: "status",
    state: pauseIt ? "paused" : "taken_over",
    message: pauseIt ? "A scan is using Presage — this screen resumes when it's done" : "Another screen took over the camera session",
  });
  if (victim.conn.session === victim) victim.conn.session = null;
  await endLocked(victim);
}

// Lifecycle held: start a session for this screen if it still wants one. After a restart the scan's recording carries
// on, so the summary still covers the whole measured window.
async function beginLocked(conn) {
  const { ws, kind, transferId } = conn;
  if (!conn.wanted || ws.readyState !== ws.OPEN) return null; // stopped or left while waiting its turn
  if (fileRunning) {
    paused.add(ws);
    send(ws, { type: "status", state: "paused", message: "Presage is measuring a recorded scan — starting in a moment" });
    return null;
  }
  await endLocked(conn.session); // the same screen starting again
  conn.session = null;
  await makeRoom(kind);
  if (!conn.wanted || ws.readyState !== ws.OPEN) return null; // stopped or left while the other session ended
  const carried = conn.carry;
  conn.carry = null;
  const { SmartSpectraSDK, FrameTransform, ProcessingStatus } = sdkModule;
  const sdk = new SmartSpectraSDK({ apiKey: API_KEY, requestedMetrics: requestedMetrics(), enableTelemetry: false });
  const session = {
    id: ++sessionCount, conn, sdk, kind, transferId, lastTs: 0, latest: {}, hint: null, postTimer: null, failed: false,
    ending: null, frames: carried?.frames ?? 0, rec: carried?.rec ?? newRecording(), markedAt: carried?.markedAt ?? Date.now(),
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
    const pulseWave = (m.cardio?.arterialPressureTrace ?? []).slice(-90).map((p) => p.value ?? 0);
    const apnea = last(m.breathing?.apnea);
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
      pulse: pulseWave,
      apnea: !!(apnea?.detected && apnea?.stable),
    });
  });
  sdk.on("validationStatus", (code, _ts, hint) => {
    session.hint = code === 0 ? null : hint || HINTS[code] || `Adjust camera (code ${code})`;
    noteValidation(session.rec, code, hint);
    // the face left the frame (or the light went): whatever was measured before is no longer the patient now
    if (code !== 0) session.latest = {};
    send(ws, { type: "validation", code, ok: code === 0, hint: session.hint });
  });
  sdk.on("processingStatus", (status) => {
    send(ws, { type: "processing", status });
    if (status === ProcessingStatus.kError) trouble(session, 8, "SmartSpectra processing stopped", false);
  });
  sdk.on("error", (code, message, retryable) => trouble(session, code, message, retryable));

  sdk.useCustomInput(FrameTransform.kNone);
  sdk.start();
  active = session;
  conn.session = session;

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
  console.log(`[bridge] ${stamp()} ${kind} session ${session.id} started${transferId ? ` for transfer ${transferId}` : ""}${carried ? " (restart)" : ""}`);
  return session;
}

// The SDK reported a problem. One that stops the session (or any it calls not retryable) gets a fresh session, twice
// at most per start from the screen, unless a new session can't help (key, configuration, credits). The screen is
// told it's restarting, then running again; a scan keeps its recording across the restart.
function trouble(session, code, message, retryable) {
  console.warn(`[bridge] ${stamp()} ${session.kind} session ${session.id}: SDK error ${code}: ${message}`);
  if (session.ending || session.failed) return; // a session on its way out may still complain
  const { conn } = session;
  if (!DEAD_ERRORS.has(code) && retryable) {
    send(conn.ws, { type: "error", code, message, retryable: true }); // the SDK carries on
    return;
  }
  session.failed = true;
  if (!FATAL_ERRORS.has(code) && conn.restarts < MAX_RESTARTS && conn.session === session) {
    conn.restarts += 1;
    send(conn.ws, { type: "status", state: "restarting", message: "Presage hit a snag — restarting it" });
    serial(async () => {
      if (conn.session !== session) return; // stopped or replaced meanwhile
      conn.carry = { kind: session.kind, rec: session.rec, markedAt: session.markedAt, frames: session.frames };
      await endLocked(session);
      conn.session = null;
      await sleep(RESTART_DELAY_MS);
      await beginLocked(conn);
    }).catch((err) => send(conn.ws, { type: "status", state: "error", message: `Could not restart SmartSpectra: ${err.message}` }));
    return;
  }
  send(conn.ws, { type: "error", code, message, retryable: !!retryable });
  send(conn.ws, { type: "status", state: "error", message: FATAL_ERRORS.has(code) ? message : `Presage stopped: ${message}` });
}

function handleFrame(session, data) {
  if (session.failed || session.ending || data.length < HEADER_BYTES) return;
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
    trouble(session, err.code ?? -1, err.message, !!err.retryable);
  }
}

// ── file mode: recorded clips the phone couldn't stream ──────────────────────────────────────────────────────────
const FILE_TIMEOUT_MS = Number(process.env.PRESAGE_TIMEOUT_MS ?? 240_000);
const MAX_UPLOAD_BYTES = 400 * 1024 * 1024; // 60 s of high-quality MJPEG at 960 px is ~150 MB
let fileJobs = 0; // clips waiting or being measured: they take their turn in `serial` like any session

async function fileVitals(clipPath) {
  const { SmartSpectraSDK, ProcessingStatus } = sdkModule;
  const rec = newRecording();
  const sdk = new SmartSpectraSDK({ apiKey: API_KEY, requestedMetrics: requestedMetrics(), enableTelemetry: false });
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
    rec.startedAt = Date.now(); // real-time playback: wall clock is clip time
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
    const result = await serial(async () => {
      fileRunning = true;
      try {
        await makeRoom("scan");
        return await fileVitals(clip);
      } finally {
        fileRunning = false;
      }
    });
    console.log("[bridge] clip measured: HR " + (result.heart_rate_bpm ?? "-") + " RR " + (result.respiration_rate_bpm ?? "-"));
    return json(res, 200, result);
  } catch (err) {
    return json(res, 500, { error: String(err.message || err) });
  } finally {
    fileJobs = Math.max(0, fileJobs - 1);
    resumePaused();
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
  // one screen: what it asked for, and its session once it's had its turn
  const conn = { ws, session: null, carry: null, kind: "monitor", transferId: undefined, wanted: false, restarts: 0 };
  send(ws, { type: "hello", sdk: sdkState, message: sdkMessage });
  ws.on("message", async (data, isBinary) => {
    if (isBinary) {
      if (conn.session && active === conn.session) handleFrame(conn.session, data);
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
      conn.kind = msg.kind === "scan" ? "scan" : "monitor";
      conn.transferId = msg.transferId;
      conn.wanted = true;
      conn.restarts = 0;
      paused.delete(ws);
      if (fileRunning || fileJobs) {
        // a recorded clip is being measured: this screen starts as soon as it's done
        paused.add(ws);
        send(ws, { type: "status", state: "paused", message: "Presage is measuring a recorded scan — starting in a moment" });
        return;
      }
      try {
        await serial(() => beginLocked(conn));
      } catch (err) {
        send(ws, { type: "status", state: "error", message: `Could not start SmartSpectra: ${err.message}` });
      }
    }
    // scan: the measured window starts now (Presage was already giving framing hints while the shot was lined up)
    if (msg.type === "mark" && conn.session) {
      conn.session.rec = newRecording();
      conn.session.markedAt = conn.session.rec.startedAt;
    }
    if (msg.type === "stop") {
      const ending = conn.session;
      const measured = ending ?? conn.carry; // mid-restart, the recording waits in `carry`
      conn.session = null;
      conn.carry = null;
      conn.wanted = false;
      if (measured?.kind === "scan" && msg.summary) {
        const seconds = Math.round((Date.now() - measured.markedAt) / 100) / 10;
        send(ws, { type: "summary", result: summary(measured.rec, { path: "live", frames: measured.frames, seconds }) });
      }
      await serial(() => endLocked(ending));
      resumePaused();
    }
  });
  ws.on("close", async () => {
    paused.delete(ws);
    const ending = conn.session;
    conn.session = null;
    conn.carry = null;
    conn.wanted = false;
    await serial(() => endLocked(ending));
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
