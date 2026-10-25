// Presage bridge client. The camera's frames go to the bridge as JPEGs over a WebSocket on this app's own address
// (/presage/ws), and Presage answers with framing hints, HR, RR, HRV and the breathing wave within seconds.
// Two uses: "monitor" (a mounted laptop or tablet, continuous; the bridge posts stable values to the engine) and
// "scan" (a phone for ~30–60 s; the bridge hands back one summary, uploaded with the clip).
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { presageBridgeUrl } from "@/app/config";

export type PresageState =
  | "starting" // opening camera / connecting
  | "running" // SDK measuring
  | "paused" // a recorded scan is using Presage; resumes by itself
  | "no_api_key" // bridge up, no PRESAGE_API_KEY
  | "offline" // bridge not running / unreachable
  | "error"; // SDK refused (auth, credits…)

export type Measure = { value: number; conf: number; stable: boolean };
export type PresageMetrics = {
  hr: Measure | null;
  rr: Measure | null;
  hrv: Measure | null;
  trace: number[]; // breathing (chest movement)
  pulse: number[]; // pulse waveform (arterial pressure trace, uncalibrated)
  apnea: boolean; // Presage detected breathing stop (stable detection)
};
/** The bridge's summary of a live scan: the whole Presage trace, sent up with the clip (engine estimates_from_bridge). */
export type PresageSummary = Record<string, unknown>;

const RGBA_MAGIC = 0x41435046; // "ACPF"
const JPEG_MAGIC = 0x4143504a; // "ACPJ"
const FPS = 30; // Presage's pulse model card asks for 25+ fps
const LONG_SIDE = 640;
const JPEG_QUALITY = 0.9; // per-frame JPEG keeps each frame's colour; no inter-frame smoothing like a video codec
const MAX_BUFFERED = 1.5 * 1024 * 1024; // on a slow uplink drop frames rather than lag behind

function header(magic: number, width: number, height: number, ms: number, payloadBytes: number): ArrayBuffer {
  const buf = new ArrayBuffer(16 + payloadBytes);
  const view = new DataView(buf);
  view.setUint32(0, magic);
  view.setUint16(4, width);
  view.setUint16(6, height);
  view.setFloat64(8, ms);
  return buf;
}

/** Raw frame: 16-byte big-endian header (u32 magic "ACPF", u16 width, u16 height, f64 capture ms), then width × height
 *  × 4 RGBA bytes. presage-bridge/src/index.js `handleFrame` decodes exactly this. */
export function encodeFrame(pixels: Uint8ClampedArray | Uint8Array, width: number, height: number, ms: number): ArrayBuffer {
  const buf = header(RGBA_MAGIC, width, height, ms, pixels.byteLength);
  new Uint8Array(buf, 16).set(pixels);
  return buf;
}

/** JPEG frame: the same header with magic "ACPJ", then the JPEG bytes (the bridge reads the size from the JPEG). */
export function encodeJpegFrame(jpeg: ArrayBuffer, width: number, height: number, ms: number): ArrayBuffer {
  const buf = header(JPEG_MAGIC, width, height, ms, jpeg.byteLength);
  new Uint8Array(buf, 16).set(new Uint8Array(jpeg));
  return buf;
}

// denied: the user or browser refused; busy: another app holds the camera (common on Windows); unavailable: none found
export type CameraState = "off" | "starting" | "on" | "denied" | "busy" | "unavailable";

export function cameraConstraints(facingMode: "user" | "environment"): MediaStreamConstraints {
  return { video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: FPS }, facingMode }, audio: false };
}

export function cameraError(err: unknown): CameraState {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotReadableError" || name === "AbortError") return "busy";
  return "unavailable";
}

// Exposure is left to the camera. Locking it (Presage's model cards prefer fixed exposure) froze many webcams and
// Android phones at a wrong, near-black value they reported, and Presage then asked for more light.

export function useCamera(enabled: boolean) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [camera, setCamera] = useState<CameraState>("off");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!enabled) return;
    let stream: MediaStream | null = null;
    let cancelled = false;
    const open = async () => {
      if (!navigator.mediaDevices?.getUserMedia) {
        setCamera("unavailable");
        return;
      }
      setCamera("starting");
      try {
        // some USB and virtual cameras reject the preferred shape; any frame size works for Presage
        const opened = await navigator.mediaDevices
          .getUserMedia(cameraConstraints("user"))
          .catch((err) => (err instanceof DOMException && err.name === "OverconstrainedError" ? navigator.mediaDevices.getUserMedia({ video: true }) : Promise.reject(err)));
        stream = opened;
        if (cancelled) {
          opened.getTracks().forEach((t) => t.stop());
          return;
        }
        if (videoRef.current) {
          videoRef.current.srcObject = opened;
          await videoRef.current.play().catch(() => undefined);
        }
        setCamera("on");
      } catch (err) {
        setCamera(cameraError(err));
      }
    };
    open();
    return () => {
      cancelled = true;
      stream?.getTracks().forEach((t) => t.stop());
    };
  }, [enabled, attempt]);

  return { videoRef, camera, retry: () => setAttempt((a) => a + 1) };
}

type FrameMeta = { captureTime?: number; expectedDisplayTime?: number };
type FrameVideo = HTMLVideoElement & {
  requestVideoFrameCallback?: (cb: (now: number, meta: FrameMeta) => void) => number;
  cancelVideoFrameCallback?: (handle: number) => void;
};

/** Send the video's frames as JPEGs, each stamped with when the camera captured it (not when it was sent), at up to
 *  30 fps. One frame in flight at a time; on a slow uplink frames are dropped, never queued. */
function streamFrames(ws: WebSocket, video: FrameVideo): () => void {
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  let busy = false;
  let stopped = false;
  let lastMs = -Infinity;
  let handle = 0;
  let timer = 0;

  const grab = (ms: number) => {
    if (stopped || busy || !ctx || ws.readyState !== WebSocket.OPEN || video.readyState < 2 || !video.videoWidth) return;
    if (ws.bufferedAmount > MAX_BUFFERED || ms - lastMs < 1000 / FPS - 3) return;
    lastMs = ms;
    const scale = Math.min(1, LONG_SIDE / Math.max(video.videoWidth, video.videoHeight));
    const w = Math.round(video.videoWidth * scale);
    const h = Math.round(video.videoHeight * scale);
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    ctx.drawImage(video, 0, 0, w, h);
    busy = true;
    canvas.toBlob(
      async (blob) => {
        if (blob && !stopped && ws.readyState === WebSocket.OPEN) ws.send(encodeJpegFrame(await blob.arrayBuffer(), w, h, ms));
        busy = false; // only now: frames must reach the bridge in capture order
      },
      "image/jpeg",
      JPEG_QUALITY,
    );
  };

  if (video.requestVideoFrameCallback) {
    const loop = (now: number, meta: FrameMeta) => {
      grab(meta.captureTime ?? meta.expectedDisplayTime ?? now);
      if (!stopped) handle = video.requestVideoFrameCallback!(loop);
    };
    handle = video.requestVideoFrameCallback(loop);
  } else {
    timer = window.setInterval(() => grab(performance.now()), 1000 / FPS);
  }
  return () => {
    stopped = true;
    if (handle) video.cancelVideoFrameCallback?.(handle);
    window.clearInterval(timer);
  };
}

/** One bridge session for a camera: framing hints and live values while it runs. */
function useBridge({ kind, transferId, video, enabled }: { kind: "monitor" | "scan"; transferId?: string; video: HTMLVideoElement | null; enabled: boolean }) {
  const [state, setState] = useState<PresageState>("starting");
  const [message, setMessage] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<PresageMetrics>({ hr: null, rr: null, hrv: null, trace: [], pulse: [], apnea: false });
  const [since, setSince] = useState<number | null>(null); // when the measured window started
  const wsRef = useRef<WebSocket | null>(null);
  const summaryRef = useRef<((s: PresageSummary | null) => void) | null>(null);

  useEffect(() => {
    if (!enabled || !video) return;
    let stopFrames: (() => void) | null = null;
    const start = () => ws.send(JSON.stringify({ type: "start", kind, transferId }));
    // WebSocket only throws synchronously for a malformed URL; connection failures arrive via onerror/onclose
    const ws = new WebSocket(presageBridgeUrl());
    wsRef.current = ws;
    ws.binaryType = "arraybuffer";
    ws.onopen = () => setState("starting");
    ws.onerror = () => setState((s) => (s === "running" ? "error" : "offline"));
    ws.onclose = () => {
      stopFrames?.();
      summaryRef.current?.(null);
      setState((s) => (s === "running" || s === "starting" ? "offline" : s));
    };
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      const msg = JSON.parse(ev.data);
      if (msg.type === "hello") {
        if (msg.sdk !== "ready") {
          setState(msg.sdk === "no_api_key" ? "no_api_key" : "error");
          setMessage(msg.message);
          return;
        }
        start();
      }
      if (msg.type === "status") {
        setMessage(msg.message ?? null);
        if (msg.state === "running") {
          setState("running");
          setSince(Date.now());
          stopFrames?.();
          stopFrames = streamFrames(ws, video);
        } else if (msg.state === "paused") {
          setState("paused");
          stopFrames?.();
        } else if (msg.state === "resume") {
          start();
        } else if (msg.state === "no_api_key") {
          setState("no_api_key");
        } else if (msg.state === "error" || msg.state === "unavailable" || msg.state === "taken_over") {
          setState("error");
          stopFrames?.();
        }
      }
      if (msg.type === "validation") setHint(msg.ok ? null : msg.hint);
      if (msg.type === "metrics") setMetrics({ hr: msg.hr, rr: msg.rr, hrv: msg.hrv, trace: msg.trace ?? [], pulse: msg.pulse ?? [], apnea: !!msg.apnea });
      if (msg.type === "summary") summaryRef.current?.(msg.result);
    };
    return () => {
      stopFrames?.();
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
      ws.close();
      wsRef.current = null;
    };
  }, [enabled, video, kind, transferId]);

  /** Scan: the measured window starts now (hints were already flowing while the shot was lined up). */
  const mark = useCallback(() => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) return;
    wsRef.current.send(JSON.stringify({ type: "mark" }));
    setSince(Date.now());
  }, []);

  /** Scan: stop measuring and get Presage's summary of the window (null if the bridge is gone). */
  const finish = useCallback(
    () =>
      new Promise<PresageSummary | null>((resolve) => {
        const ws = wsRef.current;
        if (!ws || ws.readyState !== WebSocket.OPEN) return resolve(null);
        const timer = window.setTimeout(() => resolve(null), 4000);
        summaryRef.current = (s) => {
          window.clearTimeout(timer);
          summaryRef.current = null;
          resolve(s);
        };
        ws.send(JSON.stringify({ type: "stop", summary: true }));
      }),
    [],
  );

  return { state, message, hint, metrics, since, mark, finish };
}

/** Crew monitor on a mount: continuous; the bridge posts stable, fresh values to the transfer. */
export function usePresage(transferId: string | undefined, video: HTMLVideoElement | null, cameraOn: boolean) {
  const { state, message, hint, metrics, since } = useBridge({ kind: "monitor", transferId, video, enabled: !!transferId && cameraOn });
  return { state, message, hint, metrics, since };
}

/** A phone scan: hints while framing, live values while recording, one summary at the end. */
export function usePresageScan(video: HTMLVideoElement | null, cameraOn: boolean) {
  return useBridge({ kind: "scan", video, enabled: cameraOn });
}
