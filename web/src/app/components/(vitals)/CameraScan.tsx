// F-M6.1 Camera scan UI (front/back toggle, face oval, lighting tips, countdown ring, MediaRecorder upload),
// F-M6.2 result card, F-M6.3 continuous monitoring, F-M6.4 quality gating prompt.
"use client";

import { Camera, Loader2, RefreshCw, SwitchCamera } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import SourceBadge from "@/app/components/SourceBadge";
import { api, type ScanJobStatus, type VitalsReading } from "@/lib/api";
import { toastError } from "@/lib/toast";

import styles from "./Vitals.module.scss";

type Phase = "idle" | "preview" | "recording" | "uploading" | "processing" | "done" | "failed";
const TIPS = ["Face the light — avoid backlight", "Keep the face inside the oval", "Hold the phone steady", "Patient should stay still and breathe normally"];

export default function ({
  caseId,
  onFallback,
  onReading,
  speedMultiplier = 1,
  disabled,
}: {
  caseId: string;
  onFallback: () => void;
  onReading?: (r: VitalsReading) => void;
  speedMultiplier?: number;
  disabled?: boolean;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [phase, setPhase] = useState<Phase>("idle");
  const [facing, setFacing] = useState<"user" | "environment">("user");
  const [duration, setDuration] = useState(30);
  const [left, setLeft] = useState(0);
  const [reading, setReading] = useState<VitalsReading | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [monitor, setMonitor] = useState(false);
  const [tip, setTip] = useState(0);

  const stopStream = () => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  };

  useEffect(() => stopStream, []);

  const openCamera = useCallback(
    async (mode = facing) => {
      setError(null);
      if (!navigator.mediaDevices?.getUserMedia) {
        setError("Camera not available (needs HTTPS and a supported browser).");
        onFallback();
        return false;
      }
      try {
        stopStream();
        const stream = await navigator.mediaDevices.getUserMedia({
          video: { facingMode: mode, width: { ideal: 640 }, height: { ideal: 480 } },
          audio: false,
        });
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          await videoRef.current.play().catch(() => undefined);
        }
        setPhase("preview");
        return true;
      } catch {
        setError("Camera permission denied — use manual entry instead.");
        setPhase("failed");
        onFallback();
        return false;
      }
    },
    [facing, onFallback],
  );

  const poll = async (jobId: string) => {
    for (let i = 0; i < 90; i++) {
      const s = await api<ScanJobStatus>(`/vitals/scan/${jobId}`);
      if (s.status === "done" && s.reading) return s.reading;
      if (s.status === "failed") throw new Error(s.error ?? "Scan failed");
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error("Scan timed out");
  };

  const record = async () => {
    const stream = streamRef.current;
    if (!stream) return;
    const mime = ["video/webm;codecs=vp9", "video/webm", "video/mp4"].find((m) => MediaRecorder.isTypeSupported(m)) ?? "";
    const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
    const chunks: Blob[] = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const finished = new Promise<Blob>((resolve) => {
      rec.onstop = () => resolve(new Blob(chunks, { type: rec.mimeType || "video/webm" }));
    });
    rec.start(1000);
    setPhase("recording");
    for (let s = duration; s > 0; s--) {
      setLeft(s);
      setTip((t) => (s % 5 === 0 ? (t + 1) % TIPS.length : t));
      await new Promise((r) => setTimeout(r, 1000));
    }
    rec.stop();
    const blob = await finished;
    setPhase("uploading");
    const form = new FormData();
    form.append("video", blob, blob.type.includes("mp4") ? "scan.mp4" : "scan.webm");
    try {
      const job = await api<{ job_id: string }>(`/cases/${caseId}/vitals/scan`, { method: "POST", body: form });
      setPhase("processing");
      const r = await poll(job.job_id);
      setReading(r);
      setPhase("done");
      onReading?.(r);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Scan failed");
      setPhase("failed");
      toastError(err);
    }
  };

  // F-M6.3 continuous monitoring: repeat every 2 min (sim-accelerated, min 40 s real).
  useEffect(() => {
    if (!monitor || phase !== "done") return;
    const wait = Math.max(40, 120 / Math.max(1, speedMultiplier)) * 1000;
    const t = setTimeout(async () => {
      if (!streamRef.current) {
        const ok = await openCamera();
        if (!ok) return;
      }
      record();
    }, wait);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [monitor, phase, speedMultiplier]);

  const lowQuality = reading?.low_quality || (reading?.confidence ?? 1) < 0.6;
  const busy = phase === "recording" || phase === "uploading" || phase === "processing";
  const circumference = 2 * Math.PI * 28;

  return (
    <div className="flex flex-col gap-[.75rem]">
      <div className={twMerge(styles.stage, phase === "idle" && "hidden")}>
        <video ref={videoRef} playsInline muted className={facing === "user" ? styles.mirror : undefined} />
        <div className={styles.oval} />
        {phase === "recording" && (
          <svg className={styles.ring} viewBox="0 0 64 64" aria-label={`${left} seconds left`}>
            <circle cx="32" cy="32" r="28" stroke="rgba(255,255,255,.3)" strokeWidth="5" fill="none" />
            <circle
              cx="32"
              cy="32"
              r="28"
              stroke="#fff"
              strokeWidth="5"
              fill="none"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - left / duration)}
              transform="rotate(-90 32 32)"
            />
            <foreignObject x="0" y="0" width="64" height="64">
              <span>{left}</span>
            </foreignObject>
          </svg>
        )}
        <p className={styles.tip}>{phase === "recording" ? TIPS[tip] : "Lighting tip: face a window or lamp, no backlight."}</p>
      </div>

      {error && <p className="text-[0.875rem] text-alert">{error}</p>}

      <div className="flex flex-wrap gap-[.5rem]">
        {phase === "idle" || phase === "failed" ? (
          <ButtonPrimary onClick={() => openCamera()} disabled={disabled}>
            <Camera size={20} /> Start camera
          </ButtonPrimary>
        ) : (
          <ButtonPrimary onClick={record} disabled={busy || disabled}>
            {busy ? <Loader2 size={20} className="animate-spin" /> : <Camera size={20} />}
            {phase === "recording"
              ? `Scanning… ${left}s`
              : phase === "uploading"
                ? "Uploading…"
                : phase === "processing"
                  ? "Processing…"
                  : phase === "done"
                    ? "Scan again"
                    : `Scan ${duration} s`}
          </ButtonPrimary>
        )}
        {phase !== "idle" && (
          <ButtonBase
            onClick={() => {
              const next = facing === "user" ? "environment" : "user";
              setFacing(next);
              openCamera(next);
            }}
            disabled={busy}
            aria-label="Switch camera"
          >
            <SwitchCamera size={20} />
          </ButtonBase>
        )}
        <select
          value={duration}
          onChange={(e) => setDuration(Number(e.target.value))}
          disabled={busy}
          className="h-[2.75rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.5rem]"
          aria-label="Scan duration"
        >
          <option value={30}>30 s scan</option>
          <option value={10}>10 s (demo)</option>
        </select>
        <label className="flex min-h-[2.75rem] items-center gap-[.5rem] text-[0.875rem]">
          <input type="checkbox" checked={monitor} onChange={(e) => setMonitor(e.target.checked)} className="h-[1.25rem] w-[1.25rem]" />
          Monitor (repeat every 2 min)
        </label>
      </div>

      {reading && (
        <div className={twMerge("rounded-[.75rem] border-[1px] p-[1rem]", lowQuality ? "border-warn bg-warn-soft" : "border-border")}>
          <div className="flex flex-wrap items-center gap-[1.5rem]">
            <div>
              <p className="text-[0.875rem] text-muted">Heart rate</p>
              <p className="text-[2rem] font-bold tabular-nums leading-none">{reading.heart_rate ?? "—"}</p>
            </div>
            <div>
              <p className="text-[0.875rem] text-muted">Resp rate</p>
              <p className="text-[2rem] font-bold tabular-nums leading-none">{reading.resp_rate ?? "—"}</p>
            </div>
            <div>
              <p className="text-[0.875rem] text-muted">Confidence</p>
              <p className="text-[1.25rem] font-semibold tabular-nums">{reading.confidence?.toFixed(2) ?? "—"}</p>
            </div>
            <SourceBadge kind={reading.source === "presage" ? "presage" : "mock"} />
          </div>
          {lowQuality && (
            <p className="mt-[.5rem] flex items-center gap-[.375rem] text-[0.875rem] text-warn-fg">
              <RefreshCw size={16} /> Low-quality scan — excluded from NEWS2. Please rescan in better light.
            </p>
          )}
          <p className="mt-[.5rem] text-[0.875rem] text-muted">
            Contactless HR/RR give a partial NEWS2 only — add SpO₂, BP, temperature and ACVPU when a clinician is present.
          </p>
        </div>
      )}
    </div>
  );
}
