// Stream a video file through the bridge's live path exactly as a phone does (JPEG frames over the WebSocket, at the
// clip's own pace), then print Presage's summary. Rehearse with a recorded face before trusting a stage.
//
//   node scripts/replay.mjs face.mp4 [--url ws://localhost:8787/ws] [--ffmpeg path/to/ffmpeg] [--fps 30] [--out summary.json]
//
// ffmpeg cuts the clip into JPEG frames (long side 640, like the phone); frames are sent in real time with their
// capture timestamps, so the SDK sees what a phone would send.
import { spawn } from "node:child_process";
import fs from "node:fs";

import { WebSocket } from "ws";

const args = process.argv.slice(2);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : fallback;
};
const file = args.find((a, i) => !a.startsWith("--") && !args[i - 1]?.startsWith("--"));
if (!file) {
  console.error("usage: node scripts/replay.mjs <video> [--url ws://localhost:8787/ws] [--ffmpeg ffmpeg] [--fps 30]");
  process.exit(2);
}
const url = opt("url", "ws://localhost:8787/ws");
const ffmpeg = opt("ffmpeg", process.env.FFMPEG ?? "ffmpeg");
const fps = Number(opt("fps", 30));
const out = opt("out", null); // save Presage's summary: it's what a phone uploads with its clip (form field "presage")
const JPEG_MAGIC = 0x4143504a;

// split ffmpeg's MJPEG stream into single JPEGs (each runs from FFD8 to FFD9)
function* jpegs(buf) {
  let start = buf.indexOf(Buffer.from([0xff, 0xd8]));
  while (start >= 0) {
    const end = buf.indexOf(Buffer.from([0xff, 0xd9]), start + 2);
    if (end < 0) return;
    yield buf.subarray(start, end + 2);
    start = buf.indexOf(Buffer.from([0xff, 0xd8]), end + 2);
  }
}

const frames = await new Promise((resolve, reject) => {
  const chunks = [];
  const vf = `fps=${fps},scale='if(gt(iw,ih),640,-2)':'if(gt(iw,ih),-2,640)'`;
  const p = spawn(ffmpeg, ["-loglevel", "error", "-i", file, "-an", "-vf", vf, "-f", "image2pipe", "-c:v", "mjpeg", "-q:v", "3", "-"]);
  p.stdout.on("data", (c) => chunks.push(c));
  p.stderr.on("data", (c) => process.stderr.write(c));
  p.on("error", reject);
  p.on("close", (code) => (code === 0 ? resolve([...jpegs(Buffer.concat(chunks))]) : reject(new Error(`ffmpeg exited ${code}`))));
});
console.log(`[replay] ${frames.length} frames (${(frames.length / fps).toFixed(1)} s at ${fps} fps) → ${url}`);

const ws = new WebSocket(url);
let hints = 0;
ws.on("message", (data) => {
  const msg = JSON.parse(data.toString());
  if (msg.type === "hello") {
    console.log(`[replay] bridge: ${msg.sdk} (${msg.message})`);
    if (msg.sdk !== "ready") process.exit(1);
    ws.send(JSON.stringify({ type: "start", kind: "scan" }));
  }
  if (msg.type === "status") {
    console.log(`[replay] status: ${msg.state}${msg.message ? ` — ${msg.message}` : ""}`);
    if (msg.state === "running") stream();
    if (msg.state === "error") process.exit(1);
  }
  if (msg.type === "validation" && !msg.ok && hints++ < 5) console.log(`[replay] hint: ${msg.hint}`);
  if (msg.type === "metrics" && (msg.hr?.stable || msg.rr?.stable)) {
    process.stdout.write(`\r[replay] live HR ${msg.hr?.value?.toFixed?.(0) ?? "-"}${msg.hr?.stable ? " (stable)" : ""} · RR ${msg.rr?.value?.toFixed?.(0) ?? "-"}${msg.rr?.stable ? " (stable)" : ""}   `);
  }
  if (msg.type === "summary") {
    const r = msg.result;
    console.log(`\n[replay] summary: HR ${r.heart_rate_bpm ?? "-"} · RR ${r.respiration_rate_bpm ?? "-"} · ${r.diagnostics.frames} frames in ${r.diagnostics.seconds} s`);
    console.log(`[replay] hints: ${r.hints.join(" · ") || "none"}`);
    console.log(`[replay] stable samples: pulse ${r.diagnostics.pulse_series.filter((s) => s.stable).length}, breathing ${r.diagnostics.breathing_series.filter((s) => s.stable).length}`);
    if (out) fs.writeFileSync(out, JSON.stringify(r));
    ws.close();
  }
});
ws.on("error", (err) => {
  console.error(`[replay] ${err.message}`);
  process.exit(1);
});

function stream() {
  ws.send(JSON.stringify({ type: "mark" }));
  const t0 = performance.now();
  let i = 0;
  const tick = () => {
    if (i >= frames.length) {
      ws.send(JSON.stringify({ type: "stop", summary: true }));
      return;
    }
    const jpg = frames[i];
    const buf = Buffer.alloc(16 + jpg.length);
    buf.writeUInt32BE(JPEG_MAGIC, 0);
    buf.writeUInt16BE(0, 4); // width/height come from the JPEG itself
    buf.writeUInt16BE(0, 6);
    buf.writeDoubleBE(t0 + (i * 1000) / fps, 8);
    jpg.copy(buf, 16);
    ws.send(buf);
    i += 1;
    setTimeout(tick, Math.max(0, t0 + (i * 1000) / fps - performance.now()));
  };
  tick();
}
