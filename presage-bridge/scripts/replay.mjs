// Stream a video file through the bridge's live path exactly as a phone does (JPEG frames over the WebSocket, at the
// clip's own pace), then print Presage's summary. Rehearse with a recorded face before trusting a stage.
//
//   node scripts/replay.mjs face.mp4 [--url ws://localhost:8787/ws] [--ffmpeg path/to/ffmpeg] [--fps 30]
//                                    [--seconds 30] [--out summary.json]
//
// ffmpeg cuts the clip into JPEG frames (long side 640, like the phone); frames are sent in real time with their
// capture timestamps, so the SDK sees what a phone would send. Exits 1 unless Presage reports a stable heart rate.
// `replay()` is also imported by scripts/predemo_check.mjs.
import { spawn } from "node:child_process";
import fs from "node:fs";
import { pathToFileURL } from "node:url";

import { WebSocket } from "ws";

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

function cutFrames(file, { ffmpeg, fps, seconds }) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    const vf = `fps=${fps},scale='if(gt(iw,ih),640,-2)':'if(gt(iw,ih),-2,640)'`;
    const limit = seconds ? ["-t", String(seconds)] : [];
    const p = spawn(ffmpeg, ["-loglevel", "error", ...limit, "-i", file, "-an", "-vf", vf, "-f", "image2pipe", "-c:v",
      "mjpeg", "-q:v", "3", "-"]);
    p.stdout.on("data", (c) => chunks.push(c));
    p.stderr.on("data", (c) => process.stderr.write(c));
    p.on("error", reject);
    p.on("close", (code) => (code === 0 ? resolve([...jpegs(Buffer.concat(chunks))]) : reject(new Error(`ffmpeg exited ${code}`))));
  });
}

/** Stream `file` to the bridge at `url` and resolve with Presage's summary. `on(event, detail)` hears progress:
 *  "frames" (count), "bridge" (hello message), "status", "hint", "live" (metrics with a stable value). */
export async function replay(file, { url = "ws://localhost:8787/ws", ffmpeg = process.env.FFMPEG ?? "ffmpeg", fps = 30,
  seconds = null, timeoutMs = 180_000, on = () => {} } = {}) {
  const frames = await cutFrames(file, { ffmpeg, fps, seconds });
  if (!frames.length) throw new Error(`ffmpeg found no frames in ${file}`);
  on("frames", frames.length);

  return new Promise((resolve, reject) => {
    const ws = new WebSocket(url);
    const timer = setTimeout(() => fail(new Error(`no summary from the bridge within ${timeoutMs / 1000} s`)), timeoutMs);
    let streaming = false;
    let settled = false;
    const fail = (err) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      ws.terminate();
      reject(err);
    };

    const stream = () => {
      if (streaming) return; // a resumed session reports "running" again
      streaming = true;
      ws.send(JSON.stringify({ type: "mark" }));
      const t0 = performance.now();
      let i = 0;
      const tick = () => {
        if (ws.readyState !== WebSocket.OPEN) return;
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
    };

    ws.on("message", (data) => {
      const msg = JSON.parse(data.toString());
      if (msg.type === "hello") {
        on("bridge", msg);
        if (msg.sdk !== "ready") return fail(new Error(`bridge SDK is ${msg.sdk}: ${msg.message ?? ""}`));
        ws.send(JSON.stringify({ type: "start", kind: "scan" }));
      }
      if (msg.type === "status") {
        on("status", msg);
        if (msg.state === "running") stream();
        // queued behind a recorded clip: ask again once Presage is free
        if (msg.state === "resume") ws.send(JSON.stringify({ type: "start", kind: "scan" }));
        if (msg.state === "error" || msg.state === "taken_over") fail(new Error(`bridge ${msg.state}: ${msg.message ?? "unknown"}`));
      }
      // retryable or not, a session that reported an SDK error has stopped measuring in practice
      if (msg.type === "error") fail(new Error(`Presage SDK error ${msg.code}: ${msg.message}`));
      if (msg.type === "validation" && !msg.ok) on("hint", msg.hint);
      if (msg.type === "metrics" && (msg.hr?.stable || msg.rr?.stable)) on("live", msg);
      if (msg.type === "summary") {
        settled = true;
        clearTimeout(timer);
        ws.close();
        resolve(msg.result);
      }
    });
    ws.on("error", (err) => fail(err));
    ws.on("close", (code) => fail(new Error(`the bridge closed the connection (${code}) before the summary`)));
  });
}

/** How many of the summary's pulse and breathing samples Presage marked stable. */
export function stableCounts(result) {
  const d = result?.diagnostics ?? {};
  return {
    pulse: (d.pulse_series ?? []).filter((s) => s.stable).length,
    breathing: (d.breathing_series ?? []).filter((s) => s.stable).length,
  };
}

/** The number the phone and the hospital show: the median of the stable samples (at least 3), else null. */
export function measured(result, key) {
  const vs = (result?.diagnostics?.[key] ?? []).filter((s) => s.stable).map((s) => s.value).sort((a, b) => a - b);
  return vs.length >= 3 ? Math.round(vs[Math.floor(vs.length / 2)]) : null;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const args = process.argv.slice(2);
  const opt = (name, fallback) => {
    const i = args.indexOf(`--${name}`);
    return i >= 0 ? args[i + 1] : fallback;
  };
  const file = args.find((a, i) => !a.startsWith("--") && !args[i - 1]?.startsWith("--"));
  if (!file) {
    console.error("usage: node scripts/replay.mjs <video> [--url ws://localhost:8787/ws] [--ffmpeg ffmpeg] [--fps 30] [--seconds 30] [--out summary.json]");
    process.exit(2);
  }
  const fps = Number(opt("fps", 30));
  const out = opt("out", null); // save Presage's summary: it's what a phone uploads with its clip (form field "presage")
  let hints = 0;
  try {
    const r = await replay(file, {
      url: opt("url", "ws://localhost:8787/ws"),
      ffmpeg: opt("ffmpeg", process.env.FFMPEG ?? "ffmpeg"),
      fps,
      seconds: opt("seconds", null),
      on: (event, d) => {
        if (event === "frames") console.log(`[replay] ${d} frames (${(d / fps).toFixed(1)} s at ${fps} fps)`);
        if (event === "bridge") console.log(`[replay] bridge: ${d.sdk} (${d.message})`);
        if (event === "status") console.log(`[replay] status: ${d.state}${d.message ? ` — ${d.message}` : ""}`);
        if (event === "hint" && hints++ < 5) console.log(`[replay] hint: ${d}`);
        if (event === "live") {
          process.stdout.write(`\r[replay] live HR ${d.hr?.value?.toFixed?.(0) ?? "-"}${d.hr?.stable ? " (stable)" : ""} · RR ${d.rr?.value?.toFixed?.(0) ?? "-"}${d.rr?.stable ? " (stable)" : ""}   `);
        }
      },
    });
    const stable = stableCounts(r);
    console.log(`\n[replay] summary: HR ${r.heart_rate_bpm ?? "-"} · RR ${r.respiration_rate_bpm ?? "-"} · ${r.diagnostics.frames} frames in ${r.diagnostics.seconds} s`);
    console.log(`[replay] the phone shows: HR ${measured(r, "pulse_series") ?? "-"} · RR ${measured(r, "breathing_series") ?? "-"}`);
    console.log(`[replay] hints: ${r.hints.join(" · ") || "none"}`);
    console.log(`[replay] stable samples: pulse ${stable.pulse}, breathing ${stable.breathing}`);
    if (out) fs.writeFileSync(out, JSON.stringify(r));
    process.exit(stable.pulse > 0 ? 0 : 1);
  } catch (err) {
    console.error(`[replay] ${err.message}`);
    process.exit(1);
  }
}
