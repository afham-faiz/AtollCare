// A Presage scan on a phone. While the shot is lined up, the camera streams to Presage, which answers with framing
// hints ("no face found", "too dark"); while recording, live heart rate, breathing rate and the breathing wave appear
// within seconds. It finishes by itself once Presage calls both stable after its 30 s window (or at 60 s), then sends
// the clip (for Gemini's sign check) with Presage's summary, showing what Presage measured and the upload's progress
// until it lands, and offering to send again if it doesn't. If Presage can't be reached live, it records as before
// and Presage measures the uploaded clip instead.
"use client";

import { Camera, Loader2, RotateCcw, Send, SwitchCamera, Upload } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import { Heartbeat, Trace } from "@/app/components/(vitals)/Signal";
import { ApiError, uploadForm } from "@/lib/api";
import { autoCamera, cameraConstraints, cameraError, usePresageScan, type CameraState, type PresageSummary } from "@/lib/presage";

import styles from "./ScanRecorder.module.scss";

const RING = 2 * Math.PI * 35;

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

  // a small tap when the heart rate first steadies, so whoever is filming knows without looking
  const steadied = useRef(false);
  useEffect(() => {
    if (!recording) {
      steadied.current = false;
      return;
    }
    if (hr?.stable && !steadied.current) {
      steadied.current = true;
      navigator.vibrate?.(30);
    }
  }, [recording, hr?.stable]);

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
  const talk = withAudio ? " · say what happened" : "";
  const capsule = recording
    ? live
      ? settling
        ? `Measuring · ${Math.ceil(windowSeconds - elapsed)} s${talk}`
        : `Measuring · ${left} s left${talk}`
      : `Recording · ${left} s left${talk}`
    : live
      ? "Presage is watching"
      : "Line them up inside the corners";
  const handing = phase !== "camera";
  const heart = measured(handoff?.summary ?? null, "pulse_series");
  const breaths = measured(handoff?.summary ?? null, "breathing_series");
  const hrValue = hr?.value ? Math.round(hr.value) : null;
  const rrValue = rr?.value ? Math.round(rr.value) : null;
  const blocked = camera === "denied" || camera === "unavailable" || camera === "busy";
  // one line above the shutter that follows the moment, instead of a list of rules
  const coach =
    camera === "off"
      ? "Tap to start the camera"
      : camera === "starting"
        ? "Opening the camera"
        : camera === "denied"
          ? "Camera blocked. Allow it in the address bar, or upload a video"
          : blocked
            ? "Camera unavailable. Upload a video instead"
            : recording
              ? null
              : "Arm's length away, face and chest inside the corners";
  const upload = () => fileInput.current?.click();
  const shutter = blocked ? upload : camera === "on" ? (recording ? finish : record) : () => startCamera(facing);

  return (
    <div className={styles.wrap}>
      <div className={twMerge(styles.stage, recording && styles.stageLive, live && camera === "on" && styles.stageReading)}>
        <video ref={setVideoEl} playsInline muted className={twMerge(styles.video, (camera !== "on" || handing) && styles.hidden, facing === "user" && styles.mirror)} />
        {handing ? (
          <div className={styles.result} role="status" aria-live="polite">
            {handoff?.summary && (heart !== null || breaths !== null) ? (
              <div className={styles.resultNumbers}>
                <Heartbeat bpm={heart} size="lg" />
                <p className={styles.resultValue}>
                  <span className="numeral">{heart ?? "—"}</span>
                  <span className={styles.unit}>bpm</span>
                </p>
                <p className={styles.resultSecond}>
                  Breathing <strong className="tnum">{breaths ?? "—"}</strong> a minute
                </p>
              </div>
            ) : handoff?.summary ? (
              <p className={styles.resultNote}>No steady reading this time. The video still goes, and Presage measures it after you send.</p>
            ) : null}
            {phase === "finishing" && (
              <p className={styles.resultLine}>
                <Loader2 size={16} strokeWidth={1.75} className="animate-spin" /> Getting the result
              </p>
            )}
            {phase === "sending" && (
              <div className={styles.progress}>
                <div className={styles.bar} aria-hidden>
                  <span style={{ transform: `scaleX(${progress})` }} />
                </div>
                <p className={styles.resultLine}>{progress < 1 ? `Sending the video · ${Math.round(progress * 100)}%` : "Sent · checking it"}</p>
              </div>
            )}
            {phase === "failed" && handoff && (
              <>
                <p className={styles.resultFailed}>The video didn&apos;t send: {error}</p>
                <div className={styles.resultActions}>
                  <button type="button" className={styles.pillLight} onClick={() => send(handoff)}>
                    <Send size={16} strokeWidth={1.75} /> Send again
                  </button>
                  <button
                    type="button"
                    className={styles.pillGhost}
                    onClick={() => {
                      setHandoff(null);
                      setPhase("camera");
                    }}
                  >
                    <RotateCcw size={16} strokeWidth={1.75} /> Record again
                  </button>
                </div>
              </>
            )}
          </div>
        ) : (
          <>
            <div className={styles.scrim} aria-hidden />
            {camera === "on" ? (
              <>
                <svg className={twMerge(styles.guide, recording && styles.guideLive, live && presage.hint && styles.guideHint)} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
                  <path d="M14 10 V4 Q14 0 18 0 H28" />
                  <path d="M86 10 V4 Q86 0 82 0 H72" />
                  <path d="M14 90 V96 Q14 100 18 100 H28" />
                  <path d="M86 90 V96 Q86 100 82 100 H72" />
                </svg>
                <span className={styles.capsule}>
                  <span className={twMerge(styles.dot, recording && styles.dotLive, !recording && live && styles.dotPresage)} />
                  <span className="tnum">{capsule}</span>
                </span>
                {live && presage.hint && (
                  <span className={styles.hint} role="status" key={presage.hint}>
                    {presage.hint}
                  </span>
                )}
              </>
            ) : (
              // before the camera: the instrument at rest, not an empty state
              <div className={styles.idle} aria-hidden>
                <p className={styles.idleReading}>
                  <span className="numeral">—</span>
                  <span className={styles.unit}>bpm</span>
                </p>
                <Heartbeat size="lg" waiting={camera === "off" || camera === "starting"} />
              </div>
            )}

            <div className={styles.bottom}>
              {camera === "on" && live && (
                <div className={styles.readout} aria-live="polite">
                  <div className={styles.readoutRow}>
                    <Heartbeat bpm={hr?.stable ? hr.value : null} waiting={!hr?.stable} size="sm" />
                    <p className={twMerge(styles.primary, !hr?.stable && styles.ghosted)}>
                      <span className={twMerge("numeral", styles.hrValue)}>{hrValue ?? "—"}</span>
                      <span className={styles.unit}>{hr?.stable ? "bpm · steady" : hrValue ? "bpm · settling" : "bpm"}</span>
                    </p>
                    <p className={twMerge(styles.secondary, !rr?.stable && styles.ghosted)}>
                      <span className={twMerge("numeral", styles.rrValue)}>{rrValue ?? "—"}</span>
                      <span className={styles.unit}>breaths</span>
                    </p>
                  </div>
                  <Trace values={presage.metrics.trace} tone="camera" fade dot label="Live breathing wave" className={styles.readoutWave} />
                  {presage.metrics.apnea && <span className={styles.apnea}>Presage sees a pause in breathing</span>}
                </div>
              )}
              {coach && <p className={styles.coach}>{coach}</p>}

              <div className={styles.controls}>
                {!recording && !blocked ? (
                  <button
                    type="button"
                    className={styles.roundButton}
                    onClick={() => {
                      const next = facing === "environment" ? "user" : "environment";
                      setFacing(next);
                      if (camera === "on") startCamera(next);
                    }}
                    aria-label="Switch camera"
                    title="Switch camera"
                  >
                    <SwitchCamera size={20} strokeWidth={1.75} />
                  </button>
                ) : (
                  <span />
                )}

                <button
                  type="button"
                  className={twMerge(styles.shutter, recording && styles.shutterLive, camera === "starting" && styles.shutterBusy)}
                  onClick={shutter}
                  disabled={camera === "starting" || disabled}
                  aria-label={blocked ? "Upload a video" : recording ? "Stop" : camera === "on" ? "Start measuring" : "Start the camera"}
                >
                  <svg viewBox="0 0 76 76" className={styles.ring} aria-hidden>
                    <circle cx="38" cy="38" r="35" className={styles.ringTrack} />
                    <circle cx="38" cy="38" r="35" className={styles.ringFill} style={{ strokeDasharray: RING, strokeDashoffset: RING * (1 - ring), opacity: ring > 0 ? 1 : 0 }} />
                  </svg>
                  <span className={styles.shutterCore}>
                    {blocked ? <Upload size={22} strokeWidth={1.75} /> : camera === "off" ? <Camera size={22} strokeWidth={1.75} /> : null}
                  </span>
                </button>

                {!recording && !blocked ? (
                  <button type="button" className={styles.roundButton} onClick={upload} disabled={disabled} aria-label="Upload a video" title="Upload a video">
                    <Upload size={20} strokeWidth={1.75} />
                  </button>
                ) : (
                  <span />
                )}
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
            </div>
          </>
        )}
      </div>

      {!handing && camera === "on" && !live && presage.state !== "starting" && (
        <p className={styles.fallback}>
          {presage.state === "paused"
            ? "Presage is busy with another scan. Record anyway: it measures the video after you send it."
            : "Presage isn't reachable live. Record anyway: it measures the video after you send it."}
        </p>
      )}
    </div>
  );
}
