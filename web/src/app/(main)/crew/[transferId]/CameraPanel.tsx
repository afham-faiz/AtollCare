// Mounted camera view with a face + upper-chest framing guide, Presage status and live framing hints.
"use client";

import { CameraOff, ScanFace } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { PresageState } from "@/lib/presage";

import styles from "./CameraPanel.module.scss";

const STATUS: Record<PresageState, { label: string; tone: "live" | "sim" | "wait" }> = {
  starting: { label: "Connecting to Presage…", tone: "wait" },
  running: { label: "Presage · measuring", tone: "live" },
  no_api_key: { label: "Simulated vitals · Presage key not set", tone: "sim" },
  offline: { label: "Simulated vitals · Presage bridge not running", tone: "sim" },
  error: { label: "Simulated vitals · Presage unavailable", tone: "sim" },
};

export default function ({
  videoRef,
  camera,
  presage,
  hint,
  message,
}: {
  videoRef: (el: HTMLVideoElement | null) => void;
  camera: "off" | "starting" | "on" | "denied" | "unavailable";
  presage: PresageState;
  hint: string | null;
  message: string | null;
}) {
  const status = camera === "on" ? STATUS[presage] : { label: "Simulated vitals · camera off", tone: "sim" as const };
  return (
    <div className={styles.panel}>
      <video ref={videoRef} playsInline muted className={twMerge(styles.video, camera !== "on" && styles.hidden)} />
      {camera === "on" && <div className={styles.guide} aria-hidden />}
      {camera !== "on" && (
        <div className={styles.empty}>
          {camera === "starting" ? <ScanFace size={40} /> : <CameraOff size={40} />}
          <p>
            {camera === "starting"
              ? "Opening camera…"
              : camera === "denied"
                ? "Camera permission denied"
                : "No camera available on this device"}
          </p>
          <span>Mount the camera to see the patient&apos;s face and upper chest.</span>
        </div>
      )}
      <span className={twMerge(styles.badge, styles[status.tone])} title={message ?? undefined}>
        <span className={styles.dot} />
        {status.label}
      </span>
      {camera === "on" && presage === "running" && (
        <span className={twMerge(styles.hint, !hint && styles.ok)}>{hint ?? "Good framing — hold still"}</span>
      )}
    </div>
  );
}
