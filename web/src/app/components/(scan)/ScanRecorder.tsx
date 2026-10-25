// A Presage scan on a phone. While the shot is lined up, the camera streams to Presage, which answers with framing
// hints ("no face found", "too dark"); while recording, live heart rate, breathing rate and the breathing wave appear
// within seconds. It finishes by itself once Presage calls both stable after its 30 s window (or at 60 s), then sends
// the clip (for Gemini's sign check) with Presage's summary, showing what Presage measured and the upload's progress
// until it lands, and offering to send again if it doesn't. If Presage can't be reached live, it records as before
// and Presage measures the uploaded clip instead.
"use client";

import { Camera, CameraOff, Loader2, RefreshCw, RotateCcw, Send, SwitchCamera, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import { ApiError, uploadForm } from "@/lib/api";
import { autoCamera, cameraConstraints, cameraError, usePresageScan, type CameraState, type PresageSummary } from "@/lib/presage";

import styles from "./ScanRecorder.module.scss";

const RING = 2 * Math.PI * 34;

// with the microphone on, ask for a format that names an audio codec too (some phones refuse otherwise)
function pickType(withAudio: boolean): string {
  if (typeof MediaRecorder === "undefined") return "";
  const types = withAudio
    ? ["video/mp4;codecs=avc1,mp4a.40.2", "video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/mp4", "video/webm"]
    : ["video/mp4;codecs=avc1", "video/mp4", "video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm"];
  return types.find((t) => MediaRecorder.isTypeSupported(t)) ?? "";
}

type Sample = { value: number; stable?: boolean };

// the same summary the engine makes (median of the samples Presage called stable), to show right away
function measured(summary: PresageSummary | null, key: "pulse_series" | "breathing_series"): number | null {
  const series = ((summary?.diagnostics as Record<string, Sample[]> | undefined)?.[key] ?? []).filter((s) => s.stable);
  if (series.length < 3) return null;
  const vs = series.map((s) => s.value).sort((a, b) => a - b);
  return Math.round(vs[Math.floor(vs.length / 2)]);
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

type Handoff = { clip: Blob; filename: string; summary: PresageSummary | null };

export default function <T,>({
  endpoint,
  onSent,
  maxSeconds = 60,
  windowSeconds = 30,
  defaultFacing = "environment",
  withAudio = false,
  disabled,
}: {
  endpoint: string; // where the clip goes, e.g. /intakes/{id}/scans
  onSent: (result: T) => void;
  maxSeconds?: number;
  windowSeconds?: number; // Presage's cleared measurement window (K254169)
  defaultFacing?: "environment" | "user";
  withAudio?: boolean; // record the companion's voice too: what they say while filming becomes the account
  disabled?: boolean;
}) {
  const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null);
  const stream = useRef<MediaStream | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const fileInput = useRef<HTMLInputElement>(null);
  const summary = useRef<Promise<PresageSummary | null> | null>(null);
  const [camera, setCamera] = useState<CameraState>("off");
  const [facing, setFacing] = useState(defaultFacing);
  const [recording, setRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  // after recording: finishing (Presage's summary) → sending (with progress) → done, or failed (send again)
  const [phase, setPhase] = useState<"camera" | "finishing" | "sending" | "failed">("camera");
  const [handoff, setHandoff] = useState<Handoff | null>(null);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const presage = usePresageScan(videoEl, camera === "on");
  const live = presage.state === "running";
  const hr = live ? presage.metrics.hr : null;
  const rr = live ? presage.metrics.rr : null;

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
        // the microphone only if asked, and never fatal: without it the video still records
        const s = await navigator.mediaDevices
          .getUserMedia({ ...cameraConstraints(mode), audio: withAudio })
          .catch((err) => (withAudio ? navigator.mediaDevices.getUserMedia(cameraConstraints(mode)) : Promise.reject(err)));
        stream.current = s;
        autoCamera(s);
        if (videoEl) {
          videoEl.srcObject = s;
          await videoEl.play().catch(() => undefined);
        }
        setCamera("on");
      } catch (err) {
        setCamera(cameraError(err));
      }
    },
    [stopCamera, videoEl, withAudio],
  );

  useEffect(() => stopCamera, [stopCamera]);

  const send = useCallback(
    async (h: Handoff) => {
      setHandoff(h);
      setPhase("sending");
      setProgress(0);
      setError(null);
      const form = new FormData();
      form.append("video", h.clip, h.filename);
      if (h.summary) form.append("presage", JSON.stringify(h.summary)); // measured live while recording
      try {
        const result = await uploadForm<T>(endpoint, form, setProgress);
        setPhase("camera");
        setHandoff(null);
        onSent(result);
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "The connection dropped");
        setPhase("failed");
      }
    },
    [endpoint, onSent],
  );

  const finish = useCallback(() => {
    const r = recorder.current;
    if (!r || r.state === "inactive") return;
    setPhase("finishing");
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
    const type = pickType(withAudio);
    // measured live, the clip only feeds Gemini's stills and the spoken account, so keep it small for the uplink;
    // otherwise Presage measures the clip, so keep it rich (a starved encoder smooths the pulse away)
    const bitrate = live ? 1_200_000 : 4_000_000;
    let r: MediaRecorder;
    try {
      r = new MediaRecorder(stream.current, { ...(type ? { mimeType: type } : {}), videoBitsPerSecond: bitrate });
    } catch {
      r = new MediaRecorder(stream.current); // the phone's own default format
    }
    chunks.current = [];
    r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
    r.onstop = async () => {
      setRecording(false);
      const blob = new Blob(chunks.current, { type: r.mimeType || "video/webm" });
      const ext = blob.type.includes("mp4") ? "mp4" : "webm";
      const result = (await summary.current) ?? null;
      stopCamera();
      setCamera("off");
      send({ clip: blob, filename: `scan-${new Date().toISOString().slice(11, 19).replaceAll(":", "")}.${ext}`, summary: result });
    };
    recorder.current = r;
    summary.current = null;
    if (live) presage.mark();
    r.start(1000);
    setElapsed(0);
    setRecording(true);
  };

  const left = Math.max(0, Math.ceil(maxSeconds - elapsed));
  const ring = Math.min(1, elapsed / maxSeconds);
  const settling = recording && elapsed < windowSeconds;
  const capsule = recording
    ? live
      ? `Measuring · ${settling ? `${Math.ceil(windowSeconds - elapsed)} s to a reading` : `${left} s left`}`
      : `Recording · ${left} s left`
    : live
      ? "Presage is watching · face and chest down to the belly"
      : "Face and chest down to the belly inside the corners";
  const handing = phase !== "camera";
  const heart = measured(handoff?.summary ?? null, "pulse_series");
  const breaths = measured(handoff?.summary ?? null, "breathing_series");

  return (
    <div className={styles.wrap}>
      <div className={styles.viewport}>
        <video ref={setVideoEl} playsInline muted className={twMerge(styles.video, (camera !== "on" || handing) && styles.hidden, facing === "user" && styles.mirror)} />
        {handing ? (
          <div className={styles.handoff} role="status" aria-live="polite">
            {handoff?.summary && (
              <div className={styles.handoffNumbers}>
                <span className={styles.readoutSource}>Presage · measured live</span>
                {heart !== null || breaths !== null ? (
                  <div className={styles.readoutRow}>
                    <span className={styles.reading}>
                      <span className={styles.readingValue}>{heart ?? "—"}</span>
                      <span className={styles.readingUnit}>bpm</span>
                    </span>
                    <span className={styles.reading}>
                      <span className={styles.readingValue}>{breaths ?? "—"}</span>
                      <span className={styles.readingUnit}>/min</span>
                    </span>
                  </div>
                ) : (
                  <p className={styles.handoffNote}>No steady reading this time. The video still goes; try again with more light and less movement.</p>
                )}
              </div>
            )}
            {phase === "finishing" && (
              <p className={styles.handoffLine}>
                <Loader2 size={16} className="animate-spin" /> Getting Presage&apos;s result…
              </p>
            )}
            {phase === "sending" && (
              <>
                <div className={styles.bar} aria-hidden>
                  <span style={{ transform: `scaleX(${progress})` }} />
                </div>
                <p className={styles.handoffLine}>
                  <Loader2 size={16} className="animate-spin" />
                  {progress < 1 ? `Sending the video · ${Math.round(progress * 100)}%` : "Sent · checking it…"}
                </p>
              </>
            )}
            {phase === "failed" && handoff && (
              <>
                <p className={styles.handoffFailed}>The video didn&apos;t send: {error}</p>
                <div className={styles.handoffActions}>
                  <button type="button" className={styles.startCam} onClick={() => send(handoff)}>
                    <Send size={16} /> Send again
                  </button>
                  <button
                    type="button"
                    className={styles.ghost}
                    onClick={() => {
                      setHandoff(null);
                      setPhase("camera");
                    }}
                  >
                    <RotateCcw size={16} /> Record again
                  </button>
                </div>
              </>
            )}
          </div>
        ) : camera === "on" ? (
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

      {!handing && (
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
              <circle cx="38" cy="38" r="34" className={styles.ringFill} style={{ strokeDasharray: RING, strokeDashoffset: RING * (1 - ring) }} />
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
              if (f) send({ clip: f, filename: f.name, summary: null });
              e.target.value = "";
            }}
          />
        </div>
      )}

      {!handing && (
        <ul className={styles.coach}>
          <li className={twMerge(recording && styles.coachDim)}>Prop the phone up about an arm&apos;s length or more away, so it doesn&apos;t move</li>
          <li className={twMerge(recording && styles.coachDim)}>
            Get their face <strong>and chest down to the belly</strong> in view, lit from the front: Presage won&apos;t measure without the chest
          </li>
          <li className={twMerge(settling && styles.coachNow)}>{settling ? "Keep them still and quiet until the numbers settle" : "Ask them to stay still and not talk"}</li>
          {withAudio && <li className={twMerge(recording && styles.coachNow)}>You talk: say what happened and when it started</li>}
        </ul>
      )}
      {!handing && camera === "on" && !live && presage.state !== "starting" && (
        <p className={styles.fallback}>
          {presage.state === "paused"
            ? "Presage is busy with another scan. Record anyway; it measures the video after you send it."
            : "Presage isn't reachable live from here. Record anyway; it measures the video after you send it."}
        </p>
      )}
    </div>
  );
}
