// One scan, as it lands: Presage heart and breathing rate (with how good the signal was) and Gemini's check for visible
// signs (every "seen" shows the frames it rests on). Nothing is claimed beyond what the clip supports.
"use client";

import { AlertCircle, ChevronDown, Eye, Loader2, MessageSquareQuote } from "lucide-react";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

import type { CueFinding, Scan } from "@/lib/api";
import { fmtTime } from "@/lib/format";

import styles from "./ScanResult.module.scss";

const SCORED = 0.6; // the engine's scoring gate; a vital Presage calls stable always reports at least this

// Presage's own verdict, in words: stable readings are scored; anything else is shown but never counted
function quality(stable?: boolean | null, q?: number | null): { word: string; tone: "good" | "weak" } {
  return (stable ?? (q != null && q >= SCORED)) ? { word: "Stable · scored", tone: "good" } : { word: "Not stable · not scored", tone: "weak" };
}

function Vital({ label, value, unit, q, stable, bystander }: { label: string; value?: number | null; unit: string; q?: number | null; stable?: boolean | null; bystander?: boolean }) {
  // a bystander's recording is outside Presage's cleared use: shown as an estimate, never scored
  const qual = bystander ? { word: "Estimate · not scored", tone: "weak" as const } : quality(stable, q);
  return (
    <div className={styles.vital}>
      <span className={styles.vitalLabel}>{label}</span>
      <span className={twMerge("tnum", styles.vitalValue, value == null && styles.muted, qual.tone !== "good" && styles.weakValue)}>
        {value ?? "—"}
        {value != null && <span className={styles.unit}>{unit}</span>}
      </span>
      {value != null && <span className={twMerge(styles.quality, styles[qual.tone])}>{qual.word}</span>}
    </div>
  );
}

function Frames({ finding, scan }: { finding: CueFinding; scan: Scan }) {
  const [open, setOpen] = useState<number | null>(null);
  const times = Object.fromEntries((scan.signs?.frames ?? []).map((f) => [f.index, f.t_s]));
  const frames = finding.evidence_frames.filter((i) => scan.evidence[String(i)]);
  if (!frames.length) return null;
  return (
    <div className={styles.frames}>
      <div className={styles.thumbs}>
        {frames.map((i) => (
          <button key={i} type="button" className={twMerge(styles.thumb, open === i && styles.thumbOpen)} onClick={() => setOpen(open === i ? null : i)}>
            <img src={scan.evidence[String(i)]} alt={`Frame ${i}`} />
            <span>
              Frame {i}
              {times[i] != null ? ` · ${Math.round(times[i])} s` : ""}
            </span>
          </button>
        ))}
      </div>
      {open != null && (
        <img className={styles.large} src={scan.evidence[String(open)]} alt={`Frame ${open}, enlarged`} />
      )}
    </div>
  );
}

// coach: the person who recorded is looking, so say how to get a better clip
// bystander: the companion recorded it (not trained staff with a mounted phone), so its numbers are an estimate
export default function ({ scan, tz, title, coach, bystander }: { scan: Scan; tz?: string; title?: string; coach?: boolean; bystander?: boolean }) {
  const signs = scan.signs;
  const notChecked = signs?.issues.some((i) => i.startsWith("inspection_failed"));
  const present = signs?.findings.filter((f) => f.finding === "present") ?? [];
  const absent = signs?.findings.filter((f) => f.finding === "absent") ?? [];
  const unclear = signs?.findings.filter((f) => f.finding === "cannot_assess") ?? [];
  // signs the account described: "checked and not there" is worth flagging; "couldn't tell" is only a gap
  const described = new Set(signs?.plan.cues.filter((c) => c.source === "transcript").map((c) => c.cue_id));
  const contradicted = absent.filter((f) => described.has(f.cue_id));
  const unshown = unclear.filter((f) => described.has(f.cue_id));
  const v = scan.vitals;
  const measured = !!v && (v.heart_rate_bpm != null || v.respiration_rate_bpm != null);
  // with no reading the hints are already in vitals_note; beside a reading they explain its quality
  const hints = measured ? ((v?.diagnostics as { hints?: string[] } | undefined)?.hints ?? []) : [];
  const processing = scan.status === "processing";

  return (
    <article className={styles.scan} aria-busy={processing}>
      <header className={styles.head}>
        <span className={styles.title}>{title ?? "Scan"}</span>
        <span className={styles.when}>Recorded {fmtTime(scan.at, tz)}</span>
      </header>

      {processing && (
        <p className={styles.stage} role="status">
          <Loader2 size={15} className="animate-spin" /> {scan.stage ?? "Working…"}
        </p>
      )}
      {scan.status === "failed" && (
        <p className={styles.failed}>
          <AlertCircle size={15} /> This scan couldn&apos;t be analysed. {scan.error}
        </p>
      )}

      {/* vitals */}
      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h4>Heart and breathing</h4>
          <span className={styles.source}>{bystander ? "Presage · bystander video" : "Presage · from the video"}</span>
        </div>
        {measured ? (
          <div className={styles.vitals}>
            <Vital label="Heart rate" value={v?.heart_rate_bpm} unit="bpm" q={v?.heart_rate_quality} stable={v?.heart_rate_stable} bystander={bystander} />
            <Vital label="Breathing" value={v?.respiration_rate_bpm} unit="/min" q={v?.respiration_quality} stable={v?.respiration_stable} bystander={bystander} />
          </div>
        ) : (
          <p className={styles.note}>
            {scan.vitals_note ?? (processing ? "Measuring — takes about as long as the clip." : "Not measured.")}
          </p>
        )}
        {hints.length > 0 && <p className={styles.hints}>Presage noticed: {hints.join(" · ")}</p>}
      </section>

      {/* visible signs */}
      <section className={styles.block}>
        <div className={styles.blockHead}>
          <h4>Visible signs</h4>
          <span className={styles.source}>Gemini · checked frame by frame</span>
        </div>
        {!signs ? (
          <p className={styles.note}>{processing ? "Checking the video…" : "Not checked."}</p>
        ) : notChecked ? (
          <p className={styles.note}>Not checked — Gemini isn&apos;t connected, so nothing is claimed about what the video shows.</p>
        ) : (
          <>
            {contradicted.length > 0 && (
              <p className={styles.mismatch}>
                <MessageSquareQuote size={16} className="shrink-0" />
                <span>
                  <strong>Described, but not seen in the video:</strong> {contradicted.map((f) => f.label).join(", ")}
                </span>
              </p>
            )}
            {unshown.length > 0 && (
              <p className={styles.note}>
                Described, but the video couldn&apos;t show it: {unshown.map((f) => f.label).join(", ")}
              </p>
            )}
            {present.length > 0 ? (
              <ul className={styles.present}>
                {present.map((f) => (
                  <li key={f.cue_id}>
                    <p className={styles.presentHead}>
                      <Eye size={15} className="shrink-0" />
                      <strong>{f.label}</strong>
                      <span className={styles.conf}>{Math.round(f.confidence * 100)}%</span>
                    </p>
                    <p className={styles.reason}>{f.reason}</p>
                    <Frames finding={f} scan={scan} />
                  </li>
                ))}
              </ul>
            ) : (
              <p className={styles.note}>
                {absent.length > 0
                  ? "None of the signs checked were seen."
                  : `The video didn't show enough to check these signs${coach ? " — keep their face and upper body in view" : ""}.`}
              </p>
            )}
            {absent.length > 0 && (
              <p className={styles.absent}>
                <span className={styles.absentLabel}>Checked, not seen:</span> {absent.map((f) => f.label).join(" · ")}
              </p>
            )}
            {unclear.length > 0 && (
              <details className={styles.unclear}>
                <summary>
                  Couldn&apos;t tell ({unclear.length}) <ChevronDown size={14} />
                </summary>
                <ul>
                  {unclear.map((f) => (
                    <li key={f.cue_id}>
                      <strong>{f.label}</strong> — {f.reason}
                    </li>
                  ))}
                </ul>
              </details>
            )}
          </>
        )}
      </section>
    </article>
  );
}
