// Pre-demo check: run it before going on stage. It walks the path a phone scan takes, through the public link the
// phones use, and says plainly what's broken:
//
//   engine (database, Gemini on, bridge connected) → bridge (SmartSpectra ready) → web app → public link →
//   Gemini answers → Presage measures a recorded face streamed exactly like a phone → the clip uploads and the scan
//   comes back with vitals, Gemini's sign check and the spoken account.
//
//   node scripts/predemo_check.mjs [--public https://….trycloudflare.com] [--quick] [--force]
//                                  [--clip presage-bridge/fixtures/face.mp4] [--seconds 30] [--centre dhangethi_hc]
//                                  [--web http://127.0.0.1:3001] [--engine http://127.0.0.1:8000] [--bridge http://127.0.0.1:8787]
//
// The public link is found by itself while scripts/phone_tunnel.sh runs (cloudflared's /quicktunnel). The clip is a
// face with the chest in view (Presage won't measure without it) and some speech; see presage-bridge/README.md.
// A full run takes about a minute and spends four or five Gemini requests; --quick skips the Presage and upload steps.
// The Presage step won't start while a phone is scanning or a clip is being measured (it would take the session
// over); --force runs it anyway. A continuous monitor just pauses for the check, as it does for a phone scan. The upload leaves a draft packet labelled "Pre-demo check" (drafts never reach the crew).
// Exits 1 if anything failed or couldn't be checked (--quick's left-out steps don't count).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { measured, replay, stableCounts } from "../presage-bridge/scripts/replay.mjs";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const args = process.argv.slice(2);
const flag = (name) => args.includes(`--${name}`);
const opt = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i >= 0 ? args[i + 1] : fallback;
};
const ENGINE = opt("engine", "http://127.0.0.1:8000");
const BRIDGE = opt("bridge", "http://127.0.0.1:8787");
const WEB = opt("web", "http://127.0.0.1:3001");
const CLIP = path.resolve(ROOT, opt("clip", "presage-bridge/fixtures/face.mp4"));
const CENTRE = opt("centre", "dhangethi_hc");
const SECONDS = Number(opt("seconds", 30));
const QUICK = flag("quick");
const FORCE = flag("force");

const tally = { pass: 0, warn: 0, fail: 0, skip: 0, off: 0 };
const mark = { pass: "✓", warn: "!", fail: "✗", skip: "–", off: "–" }; // off: left out on purpose (--quick)
function report(kind, name, detail) {
  tally[kind] += 1;
  console.log(`  ${mark[kind]} ${name.padEnd(14)}${detail}`);
}
const secs = (ms) => `${(ms / 1000).toFixed(1)} s`;

async function get(url, ms = 15_000) {
  const t0 = performance.now();
  const res = await fetch(url, { signal: AbortSignal.timeout(ms) });
  const text = await res.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch {
    // a page, not JSON
  }
  return { status: res.status, body, ms: performance.now() - t0 };
}

async function send(method, url, body, ms = 30_000) {
  const isForm = body instanceof FormData;
  const res = await fetch(url, {
    method,
    body: isForm ? body : JSON.stringify(body),
    headers: isForm ? {} : { "Content-Type": "application/json" },
    signal: AbortSignal.timeout(ms),
  });
  const data = await res.json().catch(() => null);
  const reason = data?.error?.message ?? data?.message ?? (typeof data?.detail === "string" ? data.detail : "");
  if (!res.ok) throw new Error(`${method} ${new URL(url).pathname} → ${res.status} ${reason}`.trim());
  return data;
}

function readEnv() {
  const file = path.join(ROOT, ".env");
  if (!fs.existsSync(file)) return {};
  const env = {};
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$/);
    if (m) env[m[1]] = m[2].replace(/^["']|["']$/g, "");
  }
  return env;
}

async function findPublicUrl() {
  const given = opt("public", process.env.PUBLIC_URL);
  if (given) return given.replace(/\/$/, "");
  // cloudflared's metrics server says which quick tunnel it opened
  for (let port = 20241; port <= 20245; port += 1) {
    try {
      const { body } = await get(`http://127.0.0.1:${port}/quicktunnel`, 1500);
      if (body?.hostname) return `https://${body.hostname}`;
    } catch {
      // not this port
    }
  }
  return null;
}

// ---------------------------------------------------------------------------------------------------------------

console.log("AtollCare pre-demo check\n");

// engine
try {
  const { body } = await get(`${ENGINE}/api/health`);
  const a = body?.adapters ?? {};
  const problems = [];
  if (!String(body?.db ?? "").endsWith(":ok")) problems.push(`database ${body?.db ?? "unknown"}`);
  if (a.gemini !== "real") problems.push(`Gemini is ${a.gemini ?? "off"} (GEMINI_MODE=real in .env)`);
  if (a.presage !== "live") problems.push(`Presage is ${a.presage ?? "off"} (bridge not heard from)`);
  report(problems.length ? "fail" : "pass", "engine", problems.length ? problems.join(" · ") : `database ${body.db} · Gemini real · Presage live`);
} catch (err) {
  report("fail", "engine", `not reachable at ${ENGINE} (${err.cause?.code ?? err.message}) — start it`);
}

// bridge
let busy = null;
try {
  const { body } = await get(`${BRIDGE}/health`);
  // a scan pauses a continuous monitor, which resumes by itself afterwards; another scan or a clip it would disturb
  if (body?.session?.kind === "scan") busy = "a phone is scanning";
  else if (body?.file_jobs) busy = "a recorded clip is being measured";
  const note = busy ? ` · busy: ${busy}` : body?.session ? " · a monitor is running (it pauses during the check)" : " · free";
  report(body?.sdk === "ready" ? "pass" : "fail", "bridge", body?.sdk === "ready"
    ? `${body.message}${note}`
    : `SmartSpectra is ${body?.sdk}: ${body?.message ?? ""}`);
} catch (err) {
  report("fail", "bridge", `not reachable at ${BRIDGE} (${err.cause?.code ?? err.message}) — start presage-bridge`);
}

// the web app and the public link: the page, the engine behind /api, the bridge behind /presage
async function checkSite(name, base, page) {
  try {
    const p = await get(`${base}${page}`, 20_000);
    const api = await get(`${base}/api/health`);
    const bridge = await get(`${base}/presage/health`);
    const bad = [p.status !== 200 && `page ${p.status}`, api.status !== 200 && `/api ${api.status}`,
      bridge.status !== 200 && `/presage ${bridge.status}`].filter(Boolean);
    report(bad.length ? "fail" : p.ms > 5000 ? "warn" : "pass", name,
      bad.length ? bad.join(" · ") : `page in ${secs(p.ms)}${p.ms > 5000 ? " (slow: restart the tunnel, or use our hotspot)" : ""} · /api and /presage reach the engine and bridge`);
    return !bad.length;
  } catch (err) {
    report("fail", name, `${base} unreachable (${err.cause?.code ?? err.message})`);
    return false;
  }
}
const webOk = await checkSite("web app", WEB, "/pre-arrival");
const PUBLIC = await findPublicUrl();
let publicOk = false;
if (PUBLIC) publicOk = await checkSite("public link", PUBLIC, `/pre-arrival?centre=${CENTRE}`);
else report("skip", "public link", "no tunnel found — run scripts/phone_tunnel.sh (or pass --public URL)");
const BASE = PUBLIC && publicOk ? PUBLIC : webOk ? WEB : null;

// Gemini, asked directly with the engine's key and model, so a used-up quota shows as one
const env = readEnv();
if (env.GEMINI_USE_ENTERPRISE === "true") {
  report("skip", "Gemini", "Vertex AI key: checked only by the upload step");
} else if (!env.GEMINI_API_KEY) {
  report("fail", "Gemini", "no GEMINI_API_KEY in .env");
} else {
  const ask = async (model) => {
    const t0 = performance.now();
    const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
      method: "POST",
      headers: { "Content-Type": "application/json", "x-goog-api-key": env.GEMINI_API_KEY },
      body: JSON.stringify({ contents: [{ parts: [{ text: "Reply with the word ready." }] }], generationConfig: { maxOutputTokens: 50 } }),
      signal: AbortSignal.timeout(30_000),
    });
    const body = await res.json().catch(() => ({}));
    return { status: res.status, body, ms: performance.now() - t0 };
  };
  const main = env.GEMINI_MODEL || "gemini-3.5-flash";
  const fallback = env.GEMINI_FALLBACK_MODEL || "gemini-flash-lite-latest";
  try {
    const r = await ask(main);
    if (r.status === 200) {
      report("pass", "Gemini", `${main} answered in ${secs(r.ms)}`);
    } else if (r.status === 429) {
      const details = r.body?.error?.details ?? [];
      const delay = details.find((d) => d.retryDelay)?.retryDelay;
      const free = JSON.stringify(details).includes("FreeTier");
      const hours = delay ? ` — resets in about ${(parseFloat(delay) / 3600).toFixed(1)} h` : "";
      report("fail", "Gemini", `${main}: quota used up${free ? " (free tier: 20 requests a day per model)" : ""}${hours}`);
    } else if (r.status >= 500) {
      const f = await ask(fallback);
      report(f.status === 200 ? "warn" : "fail", "Gemini", f.status === 200
        ? `${main} is overloaded (${r.status}); the fallback ${fallback} answered, and the app falls back the same way`
        : `${main} ${r.status} and ${fallback} ${f.status}: Google is having trouble`);
    } else {
      report("fail", "Gemini", `${main}: ${r.status} ${r.body?.error?.message ?? ""} (is the key right?)`);
    }
  } catch (err) {
    report("fail", "Gemini", `no answer (${err.cause?.code ?? err.message})`);
  }
}

// Presage, live: the recorded face streamed through the same WebSocket a phone uses
let summary = null;
if (QUICK) {
  report("off", "Presage live", "left out (--quick)");
} else if (!BASE) {
  report("skip", "Presage live", "no working web address to stream through");
} else if (!fs.existsSync(CLIP)) {
  report("fail", "Presage live", `no test clip at ${path.relative(ROOT, CLIP)}: record ~40 s of a still face with the chest in view and pass --clip`);
} else if (busy && !FORCE) {
  report("skip", "Presage live", `the bridge is in use (${busy}); this would take it over. Rerun when it's free, or with --force`);
} else {
  const ws = `${BASE.replace(/^http/, "ws")}/presage/ws`;
  const t0 = performance.now();
  const tty = process.stdout.isTTY;
  if (tty) process.stdout.write(`  … Presage live  streaming ${SECONDS} s of ${path.basename(CLIP)} to ${ws}`);
  try {
    summary = await replay(CLIP, {
      url: ws, seconds: SECONDS, timeoutMs: (SECONDS + 90) * 1000,
      on: (event, d) => {
        if (tty && event === "live") {
          const hr = d.hr?.value ? `HR ${Math.round(d.hr.value)}${d.hr.stable ? " stable" : ""}` : "HR -";
          process.stdout.write(`\r  … Presage live  ${hr} · ${Math.round((performance.now() - t0) / 1000)} s   `.padEnd(80));
        }
      },
    });
    if (tty) process.stdout.write("\r".padEnd(100) + "\r");
    const stable = stableCounts(summary);
    const d = summary.diagnostics ?? {};
    const fps = d.seconds ? d.frames / d.seconds : 0;
    // the numbers the phone shows when recording stops
    const hr = measured(summary, "pulse_series");
    const rr = measured(summary, "breathing_series");
    const vitals = `HR ${hr ?? "-"} (${stable.pulse} stable samples) · RR ${rr ?? "not stable"}${rr ? ` (${stable.breathing})` : ""}`;
    const rate = `${d.frames} frames in ${d.seconds} s (${fps.toFixed(0)} fps)`;
    if (!hr) {
      report("fail", "Presage live", `no stable heart rate · ${rate} · Presage says: ${summary.hints?.join(" · ") || "nothing"}`);
    } else {
      report(fps < 20 ? "warn" : "pass", "Presage live", `${vitals} · ${rate}${fps < 20 ? " — the uplink is dropping frames" : ""}`);
    }
  } catch (err) {
    if (tty) process.stdout.write("\r".padEnd(100) + "\r");
    report("fail", "Presage live", err.message);
  }
}

// the upload a phone makes when it stops recording, then the engine's scan: vitals, Gemini's sign check, the account
if (QUICK) {
  report("off", "upload + scan", "left out (--quick)");
} else if (!BASE || !fs.existsSync(CLIP)) {
  report("skip", "upload + scan", !BASE ? "no working web address" : "no test clip");
} else {
  try {
    const api = `${BASE}/api`;
    const intake = await send("POST", `${api}/intakes`, { health_centre_id: CENTRE });
    await send("PATCH", `${api}/intakes/${intake.id}`, { patient: { label: "Pre-demo check" } });
    const form = new FormData();
    const bytes = fs.readFileSync(CLIP);
    form.append("video", new Blob([bytes], { type: "video/mp4" }), path.basename(CLIP));
    if (summary) form.append("presage", JSON.stringify(summary)); // as the phone does after a live scan
    const t0 = performance.now();
    await send("POST", `${api}/intakes/${intake.id}/scans`, form, 120_000);
    const uploaded = performance.now() - t0;
    let i = intake;
    let scan = null;
    const deadline = Date.now() + 240_000;
    while (Date.now() < deadline) {
      i = (await get(`${api}/intakes/${intake.id}`)).body;
      scan = i?.scans?.at(-1);
      if (scan && scan.status !== "processing") break;
      await new Promise((r) => setTimeout(r, 2000));
    }
    // the spoken account is transcribed from the clip's sound alongside the scan; give it a moment to land
    for (let n = 0; n < 10 && scan?.status === "done" && !i.account; n += 1) {
      await new Promise((r) => setTimeout(r, 2000));
      i = (await get(`${api}/intakes/${intake.id}`)).body;
    }
    const took = performance.now() - t0;
    const head = `${(bytes.length / 1e6).toFixed(1)} MB up in ${secs(uploaded)} · scan ${scan?.status ?? "missing"} after ${secs(took)}`;
    if (scan?.status !== "done") {
      report("fail", "upload + scan", `${head}: ${scan?.error ?? scan?.stage ?? "still processing after 4 min"}`);
    } else {
      const v = scan.vitals;
      const vitals = v?.heart_rate_bpm
        ? `HR ${v.heart_rate_bpm}${v.heart_rate_stable ? " stable" : ""} · RR ${v.respiration_rate_bpm ?? "-"} (${summary ? "live" : "measured from the clip"})`
        : `no vitals (${scan.vitals_note ?? "no reason given"})`;
      // only a failed step matters here; other issues are Gemini's answer being tidied ("Dropped frame numbers…")
      const failed = (scan.signs?.issues ?? []).filter((x) => /_failed:/.test(x));
      const signs = !scan.signs ? "no sign check"
        : failed.length ? `sign check failed (${failed.join("; ")})` : `signs: ${scan.signs.findings.length} checked`;
      const words = i.account ? i.account.split(/\s+/).length : 0;
      const account = words ? `account: ${words} words${i.account_source === "voice" ? " transcribed" : ""}` : "no spoken account";
      const gaps = [!v?.heart_rate_bpm, !scan.signs || failed.length, !words].some(Boolean);
      report(!v?.heart_rate_bpm ? "fail" : gaps ? "warn" : "pass", "upload + scan", `${head} · ${vitals} · ${signs} · ${account} · packet ${i.code}`);
    }
  } catch (err) {
    report("fail", "upload + scan", err.message);
  }
}

const verdict = tally.fail ? "NOT ready" : tally.skip || tally.off ? "not fully checked" : tally.warn ? "ready, with warnings" : "ready";
console.log(`\n${verdict}: ${tally.pass} passed, ${tally.warn} warnings, ${tally.fail} failed, ${tally.skip} skipped`);
if (PUBLIC) console.log(`phones: ${PUBLIC}/pre-arrival?centre=${CENTRE}`);
process.exit(tally.fail || tally.skip ? 1 : 0);
