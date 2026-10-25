// The contactless instrument: a framed camera viewport with face + upper-chest guidance (what Presage needs),
// honest sensor state, and an acquisition hairline tied to the real 30 s breathing window.
"use client";

import { Camera, CameraOff, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { twMerge } from "tailwind-merge";

import LiveDot from "@/app/components/(controls)/LiveDot";
import type { CameraState, PresageMetrics, PresageState } from "@/lib/presage";

import styles from "./CameraInstrument.module.scss";

const SETTLE_MS = 30_000; // Presage's cleared measurement window (K254169) is 30 s for pulse and breathing

export type Instrument = {
  phase: "off" | "connecting" | "acquiring" | "measuring" | "demo";
  label: string;
};

const EMPTY: Partial<Record<CameraState, { title: string; text: string }>> = {
  denied: { title: "Camera access is blocked", text: "Allow the camera for this site from the icon in the address bar." },
  busy: { title: "Camera is in use", text: "Close the other app using it, then try again." },
  unavailable: { title: "No camera found", text: "Connect or mount a camera, then try again." },
  off: { title: "Camera off", text: "" },
};

// why the camera isn't measuring, in the crew's terms — the video alone is not a measurement
const NOT_MEASURING: Partial<Record<PresageState, string>> = {
  no_api_key: "Not measuring · Presage API key missing",
  offline: "Not measuring · Presage bridge offline",
  error: "Not measuring · Presage unavailable",
};

export function instrumentPhase(camera: CameraState, presage: PresageState, metrics: PresageMetrics): Instrument {
  if (camera !== "on") return { phase: "off", label: camera === "starting" ? "Opening camera" : "Camera off" };
  if (presage === "starting") return { phase: "connecting", label: "Connecting to Presage" };
  // a phone scan is using Presage; this screen picks up again by itself when it's done
  if (presage === "paused") return { phase: "connecting", label: "Paused · a scan is using Presage" };
  if (presage !== "running") return { phase: "demo", label: NOT_MEASURING[presage] ?? "Not measuring" };
  if (metrics.hr?.stable || metrics.rr?.stable) return { phase: "measuring", label: "Presage · measuring" };
  return { phase: "acquiring", label: "Presage · acquiring" };
}

export default function ({
  videoRef,
  camera,
  instrument,
  hint,
  since,
  rrStable,
  onRetry,
}: {
  videoRef: (el: HTMLVideoElement | null) => void;
  camera: CameraState;
  instrument: Instrument;
  hint: string | null;
  since: number | null;
  rrStable: boolean;
  onRetry: () => void;
}) {
  const [now, setNow] = useState(() => Date.now());
  const settling = instrument.phase === "acquiring" || (instrument.phase === "measuring" && !rrStable);
  useEffect(() => {
    if (!settling) return;
    const t = window.setInterval(() => setNow(Date.now()), 250);
    return () => window.clearInterval(t);
  }, [settling]);
  const progress = since ? Math.min(0.98, (now - since) / SETTLE_MS) : 0;
  const secondsLeft = since ? Math.max(0, Math.ceil((SETTLE_MS - (now - since)) / 1000)) : 30;
  const guideTone = instrument.phase === "demo" ? styles.guideIdle : hint ? styles.guideHint : instrument.phase === "measuring" ? styles.guideOk : "";

  return (
    <figure className={styles.instrument} aria-label="Contactless vital signs camera">
      <video ref={videoRef} playsInline muted className={twMerge(styles.video, camera !== "on" && styles.hidden)} />

      {camera === "on" && (
        <>
          <div className={styles.vignette} aria-hidden />
          <svg className={twMerge(styles.guide, guideTone)} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            {/* corner brackets around the face + chest region */}
            <path d="M28 14 V8 Q28 4 32 4 H38" />
            <path d="M72 14 V8 Q72 4 68 4 H62" />
            <path d="M28 86 V92 Q28 96 32 96 H38" />
            <path d="M72 86 V92 Q72 96 68 96 H62" />
          </svg>
          {instrument.phase === "acquiring" && <div className={styles.sweep} aria-hidden />}
        </>
      )}

      {camera !== "on" && (
        <div className={styles.empty}>
          <span className={styles.emptyIcon}>{camera === "starting" ? <Camera size={22} /> : <CameraOff size={22} />}</span>
          <p className={styles.emptyTitle}>{EMPTY[camera]?.title ?? "Opening camera…"}</p>
          {camera !== "starting" && (
            <>
              <p className={styles.emptyText}>{EMPTY[camera]?.text} Until then, heart rate and breathing are simulated.</p>
              <button type="button" onClick={onRetry} className={styles.retry}>
                <RefreshCw size={14} /> Try again
              </button>
            </>
          )}
        </div>
      )}

      <figcaption className={styles.status}>
        <LiveDot tone={instrument.phase === "measuring" ? "live" : instrument.phase === "acquiring" || instrument.phase === "connecting" ? "accent" : "idle"} />
        {instrument.label}
      </figcaption>

      {camera === "on" && instrument.phase === "demo" && (
        <span className={twMerge(styles.hint, styles.hintCalm)}>Video only · heart rate and breathing are simulated</span>
      )}
      {camera === "on" && instrument.phase !== "demo" && (
        <span className={twMerge(styles.hint, hint ? styles.hintWarn : styles.hintCalm)} key={hint ?? "calm"}>
          {hint ?? (instrument.phase === "measuring" ? (rrStable ? "Steady signal" : `Breathing settles in ${secondsLeft} s`) : "Face and chest to the belly in frame · hold still")}
        </span>
      )}

      {settling && camera === "on" && <span className={styles.progress} style={{ transform: `scaleX(${progress})` }} aria-hidden />}
    </figure>
  );
}
