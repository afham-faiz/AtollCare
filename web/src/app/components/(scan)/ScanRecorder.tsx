// A Presage scan on a phone. While the shot is lined up, the camera streams to Presage, which answers with framing
// hints ("no face found", "too dark"); while recording, live heart rate, breathing rate and the breathing wave appear
// within seconds. It finishes by itself once Presage calls both stable after its 30 s window (or at 60 s), and hands
// over the clip (for Gemini's sign check) with Presage's summary. If Presage can't be reached live, it records as
// before and Presage measures the uploaded clip instead.
"use client";

import { Camera, CameraOff, RefreshCw, SwitchCamera, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import { cameraConstraints, cameraError, lockExposure, usePresageScan, type CameraState, type PresageSummary } from "@/lib/presage";

import styles from "./ScanRecorder.module.scss";

const TYPES = ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
const RING = 2 * Math.PI * 34;

function pickType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return TYPES.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
}

function Wave({ trace, label, pulse }: { trace: number[]; label: string; pulse?: boolean }) {
  if (trace.length < 4) return <span className={styles.wave} />;
  const min = Math.min(...trace);
  const span = Math.max(...trace) - min || 1;
  const pts = trace.map((v, i) => `${(i / (trace.length - 1)) * 120},${30 - ((v - min) / span) * 26}`).join(" ");
  return (
    <svg viewBox="0 0 120 32" preserveAspectRatio="none" className={twMerge(styles.wave, pulse && styles.wavePulse)} aria-label={label}>
      <polyline points={pts} />
    </svg>
  );
}

export default function ({
  onClip,
  maxSeconds = 60,
  windowSeconds = 30,
  defaultFacing = "environment",
  withAudio = false,
  disabled,
}: {
  onClip: (clip: Blob, filename: string, presage: PresageSummary | null) => void;
  maxSeconds?: number;
  windowSeconds?: number; // Presage's cleared measurement window (K254169)
  defaultFacing?: "environment" | "user";
  withAudio?: boolean; // record the companion's voice too: what they say while filming becomes the account
  disabled?: boolean;
}) {
  const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const unlock = useRef<(() => void) | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const summary = useRef<Promise<PresageSummary | null> | null>(null);
  const [camera, setCamera] = useState<CameraState>("off");
  const [facing, setFacing] = useState(defaultFacing);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const presage = usePresageScan(videoEl, camera === "on");
  const live = presage.state === "running";
  const hr = live ? presage.metrics.hr : null;
  const rr = live ? presage.metrics.rr : null;

  const stopCamera = useCallback(() => {
    unlock.current?.();
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
  }, []);

  const startCamera = useCallback(
    async (mode: "environment" | "user") => {
      if (!navigator.mediaDevices?.getUserMedia) return setCamera("unavailable");
      setCamera("starting");
      stopCamera();
      try {
        // the microphone only if asked, and never fatal: without it the video still records
        const s = await navigator.mediaDevices
          .getUserMedia({ ...cameraConstraints(mode), audio: withAudio })
          .catch((err) => (withAudio ? navigator.mediaDevices.getUserMedia(cameraConstraints(mode)) : Promise.reject(err)));
        stream.current = s;
        if (videoEl) {
          videoEl.srcObject = s;
          await videoEl.play().catch(() => undefined);
        }
        unlock.current = lockExposure(s);
        setCamera("on");
      } catch (err) {
        setCamera(cameraError(err));
      }
    },
    [stopCamera, videoEl, withAudio],
  );

  useEffect(() => stopCamera, [stopCamera]);

  const finish = useCallback(() => {
    const r = recorder.current;
    if (!r || r.state === "inactive") return;
    summary.current = live ? presage.finish() : Promise.resolve(null);
    r.stop();
  }, [live, presage]);

  useEffect(() => {
    if (!recording) return;
    const started = Date.now();
    const t = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 200);
    return () => window.clearInterval(t);
  }, [recording]);

  // done when Presage calls both stable after its window, or at the limit
  useEffect(() => {
    if (!recording) return;
    if (elapsed >= maxSeconds || (elapsed >= windowSeconds && hr?.stable && rr?.stable)) finish();
  }, [recording, elapsed, maxSeconds, windowSeconds, hr?.stable, rr?.stable, finish]);

  const record = () => {
    if (!stream.current) return;
    const type = pickType();
    // measured live, the clip only feeds Gemini's stills; otherwise Presage measures the clip, so keep it rich
    // (the pulse is a colour change of a fraction of a percent, and a starved encoder smooths it away)
    const bitrate = live ? 2_500_000 : 6_000_000;
    const r = new MediaRecorder(stream.current, { ...(type ? { mimeType: type } : {}), videoBitsPerSecond: bitrate });
    chunks.current = [];
    r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    r.onstop = async () => {
      setRecording(false);
      const blob = new Blob(chunks.current, { type: r.mimeType || "video/webm" });
      const ext = blob.type.includes("mp4") ? "mp4" : "webm";
      const result = (await summary.current) ?? null;
      stopCamera();
      setCamera("off");
      onClip(blob, `scan-${new Date().toISOString().slice(11, 19).replaceAll(":", "")}.${ext}`, result);
    };
    recorder.current = r;
    summary.current = null;
    if (live) presage.mark();
    r.start(1000);
    setElapsed(0);
    setRecording(true);
  };

  const left = Math.max(0, Math.ceil(maxSeconds - elapsed));
  const progress = Math.min(1, elapsed / maxSeconds);
  const settling = recording && elapsed < windowSeconds;
  const capsule = recording
    ? live
      ? `Measuring · ${settling ? `${Math.ceil(windowSeconds - elapsed)} s to a reading` : `${left} s left`}`
      : `Recording · ${left} s left`
    : live
      ? "Presage is watching · line up face and chest"
      : "Face and upper chest inside the corners";

  return (
    <div className={styles.wrap}>
      <div className={styles.viewport}>
        <video ref={setVideoEl} playsInline muted className={twMerge(styles.video, camera !== "on" && styles.hidden, facing === "user" && styles.mirror)} />
        {camera === "on" ? (
          <>
            <svg className={twMerge(styles.guide, recording && styles.guideLive, live && presage.hint && styles.guideHint)} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
              <path d="M24 16 V8 Q24 4 28 4 H36" />
              <path d="M76 16 V8 Q76 4 72 4 H64" />
              <path d="M24 84 V92 Q24 96 28 96 H36" />
              <path d="M76 84 V92 Q76 96 72 96 H64" />
            </svg>
            <span className={styles.capsule}>
              <span className={twMerge(styles.dot, recording && styles.dotLive, !recording && live && styles.dotPresage)} />
              {capsule}
            </span>
            {live && presage.hint && (
              <span className={styles.hint} role="status" key={presage.hint}>
                {presage.hint}
              </span>
            )}
            {live && (
              <div className={styles.readout} aria-live="polite">
                <span className={styles.readoutSource}>Presage · live</span>
                <div className={styles.readoutRow}>
                  <span className={twMerge(styles.reading, !hr?.stable && styles.readingSettling)}>
                    <span className={styles.readingValue}>{hr?.stable ? Math.round(hr.value) : "—"}</span>
                    <span className={styles.readingUnit}>bpm</span>
                  </span>
                  <Wave trace={presage.metrics.pulse} label="Live pulse waveform" pulse />
                </div>
                <div className={styles.readoutRow}>
                  <span className={twMerge(styles.reading, !rr?.stable && styles.readingSettling)}>
                    <span className={styles.readingValue}>{rr?.stable ? Math.round(rr.value) : "—"}</span>
                    <span className={styles.readingUnit}>/min</span>
                  </span>
                  <Wave trace={presage.metrics.trace} label="Live breathing waveform" />
                </div>
                {presage.metrics.apnea && <span className={styles.apneaLive}>Presage sees a pause in breathing</span>}
              </div>
            )}
          </>
        ) : (
          <div className={styles.empty}>
            <span className={styles.emptyIcon}>{camera === "denied" || camera === "unavailable" || camera === "busy" ? <CameraOff size={22} /> : <Camera size={22} />}</span>
            <p className={styles.emptyTitle}>
              {camera === "starting"
                ? "Opening camera…"
                : camera === "denied"
                  ? "Camera access is blocked"
                  : camera === "unavailable" || camera === "busy"
                    ? "No camera available"
                    : "Measure with the camera"}
            </p>
            {camera === "denied" && <p className={styles.emptyText}>Allow the camera from the icon in the address bar, or upload a video instead.</p>}
            {camera === "off" && <p className={styles.emptyText}>Heart and breathing rate from the camera, no contact. About 30–60 seconds.</p>}
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
          aria-label={recording ? "Stop" : "Start measuring"}
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
            if (f) onClip(f, f.name, null);
            e.target.value = "";
          }}
        />
      </div>

      <ul className={styles.coach}>
        <li className={twMerge(recording && styles.coachDim)}>Prop the phone up so it doesn&apos;t move</li>
        <li className={twMerge(recording && styles.coachDim)}>Keep their face and upper chest in view, in good light</li>
        <li className={twMerge(settling && styles.coachNow)}>{settling ? "Keep them still and quiet until the numbers settle" : "Ask them to stay still and not talk"}</li>
        {withAudio && <li className={twMerge(recording && styles.coachNow)}>You talk: say what happened and when it started</li>}
      </ul>
      {camera === "on" && !live && presage.state !== "starting" && (
        <p className={styles.fallback}>
          {presage.state === "paused"
            ? "Presage is busy with another scan. Record anyway; it measures the video after you send it."
            : "Presage isn't reachable live from here. Record anyway; it measures the video after you send it."}
        </p>
      )}
    </div>
  );
}
