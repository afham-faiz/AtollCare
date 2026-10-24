// Thin HTTP wrapper around the SmartSpectra Node SDK.
// POST /vitals  (raw video bytes) -> { mode, heart_rate_bpm, respiration_rate_bpm, confidence, issues }
// GET  /health
//
// PRESAGE_MODE=mock (default) needs no key and no video decoding.
// PRESAGE_MODE=sdk  runs the real SDK with PRESAGE_API_KEY.  TODO(presage-verify): not yet run against a real video.

const http = require("node:http");
const { execFile } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");

const PORT = Number(process.env.PRESAGE_SIDECAR_PORT || 3001);
const MODE = (process.env.PRESAGE_MODE || "mock").toLowerCase();
const API_KEY = process.env.PRESAGE_API_KEY || "";
const SDK_TIMEOUT_MS = Number(process.env.PRESAGE_TIMEOUT_MS || 240_000);
const MAX_BYTES = 200 * 1024 * 1024;

function mockVitals() {
  const jitter = (n) => Math.round((Math.random() * 2 - 1) * n);
  return {
    mode: "mock",
    heart_rate_bpm: 84 + jitter(3),
    respiration_rate_bpm: 18 + jitter(1),
    confidence: 0.9,
    issues: [],
  };
}

// Most recent sample of a MeasurementWithConfidence[] series.
function latest(series) {
  const last = series && series.length ? series[series.length - 1] : null;
  if (!last || last.value == null) return null;
  return { value: last.value, confidence: (last.confidence ?? 0) / 100, stable: !!last.stable };
}

async function sdkVitals(videoPath) {
  // Required lazily so mock mode works even if the native runtime fails to load.
  const { SmartSpectraSDK, ValidationCode, ProcessingStatus, breathingMetrics, cardioMetrics } = require("@smartspectra/node-sdk");
  const { decodeMetrics } = require("@smartspectra/node-sdk/messages");

  const codeNames = Object.fromEntries(Object.entries(ValidationCode).map(([name, code]) => [code, name]));
  const issues = new Set();
  const validationCounts = {};
  const pulseSeries = [];
  const breathingSeries = [];
  let firstTs = null;
  let pulse = null;
  let breathing = null;

  const sdk = new SmartSpectraSDK({
    apiKey: API_KEY,
    requestedMetrics: [...breathingMetrics, ...cardioMetrics],
    enableTelemetry: false,
  });

  try {
    const done = new Promise((resolve, reject) => {
      let sawRunning = false;
      const timer = setTimeout(() => reject(new Error("SDK timed out")), SDK_TIMEOUT_MS);
      const finish = (fn, arg) => { clearTimeout(timer); fn(arg); };

      sdk.on("processingStatus", (status) => {
        if (status === ProcessingStatus.kRunning) sawRunning = true;
        if (status === ProcessingStatus.kError) finish(reject, new Error("SDK processing error"));
        if (status === ProcessingStatus.kIdle && sawRunning) finish(resolve);
      });
      sdk.on("error", (code, message) => finish(reject, new Error(`SDK error ${code}: ${message}`)));
      sdk.on("validationStatus", (code) => {
        const name = codeNames[code] || `code_${code}`;
        validationCounts[name] = (validationCounts[name] || 0) + 1;
        if (code !== ValidationCode.kOk) issues.add(name);
      });
      sdk.on("metrics", (buf, timestampUs) => {
        const m = decodeMetrics(buf);
        if (firstTs === null) firstTs = timestampUs;
        const t_s = Math.round(((timestampUs - firstTs) / 1e6) * 10) / 10;
        const p = latest(m.cardio && m.cardio.pulseRate);
        const b = latest(m.breathing && m.breathing.rate);
        if (p) { pulse = p; pulseSeries.push({ t_s, value: p.value, confidence: p.confidence, stable: p.stable }); }
        if (b) { breathing = b; breathingSeries.push({ t_s, value: b.value, confidence: b.confidence, stable: b.stable }); }
      });
    });

    // start() emits events synchronously, so mark `done` handled before it can reject.
    done.catch(() => {});
    // Real-time pace: as-fast-as-possible playback drops frames and loses the face.
    sdk.useFile(videoPath, { interframeDelayMs: 33 });
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
    diagnostics: {
      validation_counts: validationCounts,
      pulse_series: thin(pulseSeries),
      breathing_series: thin(breathingSeries),
    },
  };
}

// Keep logs small: at most ~200 points per series.
function thin(series, max = 200) {
  if (series.length <= max) return series;
  const step = Math.ceil(series.length / max);
  return series.filter((_, i) => i % step === 0 || i === series.length - 1);
}

// The SDK's bundled FFmpeg could not open H.264 .mp4 (phone video) but reads MJPEG .avi,
// so every upload is converted first. Also applies phone rotation and caps the long side at 1280px (keeps portrait/landscape).
function toSdkReadable(input, output) {
  const ffmpeg = process.env.FFMPEG_PATH || "ffmpeg";
  const args = ["-y", "-loglevel", "error", "-i", input, "-an", "-vf", "scale='if(gt(iw,ih),min(1280,iw),-2)':'if(gt(iw,ih),-2,min(1280,ih))'", "-c:v", "mjpeg", "-q:v", "4", output];
  return new Promise((resolve, reject) => {
    execFile(ffmpeg, args, { timeout: 120_000 }, (err, _out, stderr) =>
      err ? reject(new Error(`ffmpeg conversion failed: ${(stderr || err.message).trim()}`)) : resolve());
  });
}

function readBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let size = 0;
    req.on("data", (c) => {
      size += c.length;
      if (size > MAX_BYTES) { reject(new Error("payload too large")); req.destroy(); return; }
      chunks.push(c);
    });
    req.on("end", () => resolve(Buffer.concat(chunks)));
    req.on("error", reject);
  });
}

function send(res, status, body) {
  res.writeHead(status, { "content-type": "application/json" });
  res.end(JSON.stringify(body));
}

const server = http.createServer(async (req, res) => {
  if (req.method === "GET" && req.url === "/health") return send(res, 200, { ok: true, mode: MODE });
  if (req.method !== "POST" || req.url !== "/vitals") return send(res, 404, { error: "not found" });

  let tmp, converted;
  try {
    const body = await readBody(req);
    if (!body.length) return send(res, 400, { error: "empty video body" });

    if (MODE === "mock") {
      await new Promise((r) => setTimeout(r, 300));
      return send(res, 200, mockVitals());
    }
    if (!API_KEY) return send(res, 500, { error: "PRESAGE_API_KEY not set" });

    const id = crypto.randomUUID();
    tmp = path.join(os.tmpdir(), `presage-${id}.upload`);
    converted = path.join(os.tmpdir(), `presage-${id}.avi`);
    fs.writeFileSync(tmp, body);
    await toSdkReadable(tmp, converted);
    return send(res, 200, await sdkVitals(converted));
  } catch (err) {
    return send(res, 500, { error: String(err.message || err) });
  } finally {
    for (const f of [tmp, converted]) if (f) fs.rm(f, { force: true }, () => {});
  }
});

// A native SDK failure must not take the whole sidecar down.
process.on("unhandledRejection", (err) => console.error("unhandledRejection:", err));

server.listen(PORT, "127.0.0.1", () => console.log(`presage sidecar [${MODE}] on http://127.0.0.1:${PORT}`));
