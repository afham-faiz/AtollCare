// Presage bridge client: opens the camera, streams RGBA frames to the local bridge over WebSocket, and receives live
// HR / RR / HRV, the breathing waveform and framing hints from the SmartSpectra SDK. Video never leaves the device.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { PRESAGE_BRIDGE_URL } from "@/app/config";

export type PresageState =
  | "starting" // opening camera / connecting
  | "running" // SDK measuring
  | "no_api_key" // bridge up, no PRESAGE_API_KEY
  | "offline" // bridge not running
  | "error"; // SDK refused (auth, credits…)

export type Measure = { value: number; conf: number; stable: boolean };
export type PresageMetrics = { hr: Measure | null; rr: Measure | null; hrv: Measure | null; trace: number[] };

const FRAME_MAGIC = 0x41435046;
const FRAME_WIDTH = 640;
const FPS = 20;
const MAX_BUFFERED = 4 * 1024 * 1024;

// denied: the user or browser refused; busy: another app holds the camera (common on Windows); unavailable: none found
export type CameraState = "off" | "starting" | "on" | "denied" | "busy" | "unavailable";

const PREFERRED: MediaStreamConstraints = {
  video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: "user" },
  audio: false,
};

function cameraError(err: unknown): CameraState {
  const name = err instanceof DOMException ? err.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotReadableError" || name === "AbortError") return "busy";
  return "unavailable";
}

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
          .getUserMedia(PREFERRED)
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

export function usePresage(transferId: string | undefined, video: HTMLVideoElement | null, cameraOn: boolean) {
  const [state, setState] = useState<PresageState>("starting");
  const [message, setMessage] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [metrics, setMetrics] = useState<PresageMetrics>({ hr: null, rr: null, hrv: null, trace: [] });
  const [since, setSince] = useState<number | null>(null); // when the SDK started measuring (for the 30 s window)
  const wsRef = useRef<WebSocket | null>(null);

  const sendFrames = useCallback((ws: WebSocket, el: HTMLVideoElement) => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d", { willReadFrequently: true });
    const timer = window.setInterval(() => {
      if (!ctx || ws.readyState !== WebSocket.OPEN || el.readyState < 2 || !el.videoWidth) return;
      if (ws.bufferedAmount > MAX_BUFFERED) return; // drop frames rather than lag
      const w = FRAME_WIDTH;
      const h = Math.round((FRAME_WIDTH * el.videoHeight) / el.videoWidth);
      if (canvas.width !== w || canvas.height !== h) {
        canvas.width = w;
        canvas.height = h;
      }
      ctx.drawImage(el, 0, 0, w, h);
      const pixels = ctx.getImageData(0, 0, w, h).data;
      const buf = new ArrayBuffer(16 + pixels.byteLength);
      const view = new DataView(buf);
      view.setUint32(0, FRAME_MAGIC);
      view.setUint16(4, w);
      view.setUint16(6, h);
      view.setFloat64(8, performance.now());
      new Uint8Array(buf, 16).set(pixels);
      ws.send(buf);
    }, 1000 / FPS);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!transferId || !cameraOn || !video) return;
    let stopFrames: (() => void) | null = null;
    // WebSocket only throws synchronously for a malformed URL; connection failures arrive via onerror/onclose
    const ws = new WebSocket(PRESAGE_BRIDGE_URL);
    wsRef.current = ws;
    ws.binaryType = "arraybuffer";
    ws.onerror = () => setState((s) => (s === "running" ? "error" : "offline"));
    ws.onclose = () => setState((s) => (s === "running" ? "offline" : s === "starting" ? "offline" : s));
    ws.onmessage = (ev) => {
      if (typeof ev.data !== "string") return;
      const msg = JSON.parse(ev.data);
      if (msg.type === "hello") {
        if (msg.sdk !== "ready") {
          setState(msg.sdk === "no_api_key" ? "no_api_key" : "error");
          setMessage(msg.message);
          return;
        }
        ws.send(JSON.stringify({ type: "start", transferId }));
      }
      if (msg.type === "status") {
        setMessage(msg.message ?? null);
        if (msg.state === "running") {
          setState("running");
          setSince(Date.now());
          stopFrames?.();
          stopFrames = sendFrames(ws, video);
        } else if (msg.state === "no_api_key") {
          setState("no_api_key");
        } else if (msg.state === "error" || msg.state === "unavailable" || msg.state === "taken_over") {
          setState("error");
          stopFrames?.();
        }
      }
      if (msg.type === "validation") setHint(msg.ok ? null : msg.hint);
      if (msg.type === "metrics") setMetrics({ hr: msg.hr, rr: msg.rr, hrv: msg.hrv, trace: msg.trace ?? [] });
    };
    return () => {
      stopFrames?.();
      if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: "stop" }));
      ws.close();
      wsRef.current = null;
    };
  }, [transferId, cameraOn, video, sendFrames]);

  return { state, message, hint, metrics, since };
}
