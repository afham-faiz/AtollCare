// Records one ~60 s clip for a scan: Presage needs a steady phone (propped up, not handheld), face and upper chest in
// view, and a still, quiet patient; breathing rate needs 30 s or more. The clip goes nowhere until it's handed over.
"use client";

import { Camera, CameraOff, RefreshCw, SwitchCamera, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import styles from "./ScanRecorder.module.scss";

type CameraState = "off" | "starting" | "on" | "denied" | "unavailable";
const TYPES = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
const RING = 2 * Math.PI * 34;

function pickType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return TYPES.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
}

export default function ({
  onClip,
  maxSeconds = 60,
  breathingSeconds = 30,
  defaultFacing = "environment",
  disabled,
}: {
  onClip: (clip: Blob, filename: string) => void;
  maxSeconds?: number;
  breathingSeconds?: number;
  defaultFacing?: "environment" | "user";
  disabled?: boolean;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const [camera, setCamera] = useState<CameraState>("off");
  const [facing, setFacing] = useState(defaultFacing);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);

  const stopCamera = useCallback(() => {
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  const startCamera = useCallback(
    async (mode: "environment" | "user") => {
      if (!navigator.mediaDevices?.getUserMedia) return setCamera("unavailable");
      setCamera("starting");
      stopCamera();
      try {
        const s = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: mode, width: { ideal: 1280 }, height: { ideal: 720 } },
          audio: false,
        });
        stream.current = s;
        if (video.current) {
          video.current.srcObject = s;
          await video.current.play().catch(() => undefined);
        }
        setCamera("on");
      } catch (err) {
        setCamera(err instanceof DOMException && (err.name === "NotAllowedError" || err.name === "SecurityError") ? "denied" : "unavailable");
      }
    },
    [stopCamera],
  );

  useEffect(() => stopCamera, [stopCamera]);

  const finish = useCallback(() => {
    if (recorder.current && recorder.current.state !== "inactive") recorder.current.stop();
  }, []);

  useEffect(() => {
    if (!recording) return;
    const started = Date.now();
    const t = window.setInterval(() => {
      const s = (Date.now() - started) / 1000;
      setElapsed(s);
      if (s >= maxSeconds) finish();
    }, 200);
    return () => window.clearInterval(t);
  }, [recording, maxSeconds, finish]);

  const record = () => {
    if (!stream.current) return;
    const type = pickType();
    const r = new MediaRecorder(stream.current, { ...(type ? { mimeType: type } : {}), videoBitsPerSecond: 2_500_000 });
    chunks.current = [];
    r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    r.onstop = () => {
      setRecording(false);
      const blob = new Blob(chunks.current, { type: r.mimeType || "video/webm" });
      const ext = blob.type.includes("mp4") ? "mp4" : "webm";
      stopCamera();
      setCamera("off");
      onClip(blob, `scan-${new Date().toISOString().slice(11, 19).replaceAll(":", "")}.${ext}`);
    };
    recorder.current = r;
    r.start(1000);
    setElapsed(0);
    setRecording(true);
  };

  const left = Math.max(0, Math.ceil(maxSeconds - elapsed));
  const progress = Math.min(1, elapsed / maxSeconds);
  const breathingOk = elapsed >= breathingSeconds;

  return (
    <div className={styles.wrap}>
      <div className={styles.viewport}>
        <video ref={video} playsInline muted className={twMerge(styles.video, camera !== "on" && styles.hidden, facing === "user" && styles.mirror)} />
        {camera === "on" ? (
          <>
            <svg className={twMerge(styles.guide, recording && styles.guideLive)} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
              <path d="M24 16 V8 Q24 4 28 4 H36" />
              <path d="M76 16 V8 Q76 4 72 4 H64" />
              <path d="M24 84 V92 Q24 96 28 96 H36" />
              <path d="M76 84 V92 Q76 96 72 96 H64" />
            </svg>
            <span className={styles.capsule}>
              <span className={twMerge(styles.dot, recording && styles.dotLive)} />
              {recording ? `Recording · ${left} s left` : "Face and upper chest inside the corners"}
            </span>
          </>
        ) : (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>{camera === "denied" || camera === "unavailable" ? <CameraOff size={22} /> : <Camera size={22} />}</span>
            <p className={styles.emptyTitle}>
              {camera === "starting" ? "Opening camera…" : camera === "denied" ? "Camera access is blocked" : camera === "unavailable" ? "No camera available" : "Record about 60 seconds"}
            </p>
            {camera === "denied" && <p className={styles.emptyText}>Allow the camera from the icon in the address bar, or upload a video instead.</p>}
            {camera !== "starting" && (
              <button type="button" className={styles.startCam} onClick={() => startCamera(facing)} disabled={disabled}>
                {camera === "off" ? <Camera size={16} /> : <RefreshCw size={16} />} {camera === "off" ? "Turn on camera" : "Try again"}
              </button>
            )}
          </div>
        )}
      </div>

      <div className={styles.controls}>
        <button
          type="button"
          className={styles.flip}
          onClick={() => {
            const next = facing === "environment" ? "user" : "environment";
            setFacing(next);
            if (camera === "on") startCamera(next);
          }}
          disabled={recording}
          aria-label="Switch camera"
          title="Switch camera"
        >
          <SwitchCamera size={20} />
        </button>

        <button
          type="button"
          className={twMerge(styles.record, recording && styles.recordLive)}
          onClick={recording ? finish : record}
          disabled={camera !== "on" || disabled}
          aria-label={recording ? "Stop recording" : "Start recording"}
        >
          <svg viewBox="0 0 76 76" className={styles.ring} aria-hidden>
            <circle cx="38" cy="38" r="34" className={styles.ringTrack} />
            <circle cx="38" cy="38" r="34" className={styles.ringFill} style={{ strokeDasharray: RING, strokeDashoffset: RING * (1 - progress) }} />
          </svg>
          <span className={styles.recordCore} />
        </button>

        <button type="button" className={styles.flip} onClick={() => fileInput.current?.click()} disabled={recording || disabled} aria-label="Upload a video" title="Upload a video">
          <Upload size={20} />
        </button>
        <input
          ref={fileInput}
          type="file"
          accept="video/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onClip(f, f.name);
            e.target.value = "";
          }}
        />
      </div>

      <ul className={styles.coach}>
        <li className={twMerge(recording && styles.coachDim)}>Prop the phone up so it doesn&apos;t move</li>
        <li className={twMerge(recording && styles.coachDim)}>Keep their face and upper chest in view, in good light</li>
        <li className={twMerge(recording && !breathingOk && styles.coachNow)}>
          {recording && !breathingOk ? `Keep still and quiet — breathing needs ${Math.ceil(breathingSeconds - elapsed)} s more` : "Ask them to stay still and not talk"}
        </li>
      </ul>
    </div>
  );
}
