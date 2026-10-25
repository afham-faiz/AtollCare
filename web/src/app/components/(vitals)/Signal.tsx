// The two shapes every Presage reading is drawn with: a heart in soft rings that beats at the measured rate (and only
// once the rate is steady), and a smooth trace of the signal itself. Used on the phone scan, the crew monitor and the
// hospital card.
import { twMerge } from "tailwind-merge";

import { areaPath, project, smoothPath } from "@/lib/curves";

import styles from "./Signal.module.scss";

/** A heart in concentric rings. With a steady rate it beats at that rate; waiting, it breathes slowly; otherwise it rests. */
export function Heartbeat({
  bpm,
  waiting = false,
  tone = "camera",
  size = "md",
  className,
}: {
  bpm?: number | null;
  waiting?: boolean;
  tone?: "camera" | "card";
  size?: "sm" | "md" | "lg";
  className?: string;
}) {
  const beating = !!bpm && bpm > 20 && bpm < 240;
  return (
    <span
      className={twMerge(styles.heart, styles[tone], styles[size], beating ? styles.beating : waiting && styles.waiting, className)}
      style={beating ? ({ "--beat": `${(60 / bpm).toFixed(3)}s` } as React.CSSProperties) : undefined}
      aria-hidden
    >
      <span className={styles.ring} />
      <span className={styles.ring} />
      <span className={styles.core}>
        <svg viewBox="0 0 24 24">
          <path d="M12 20.5s-7.5-4.6-9.3-9.4C1.4 7.7 3.7 4.5 7 4.5c2 0 3.5 1.1 5 3 1.5-1.9 3-3 5-3 3.3 0 5.6 3.2 4.3 6.6-1.8 4.8-9.3 9.4-9.3 9.4Z" />
        </svg>
      </span>
    </span>
  );
}

/** A smooth trace of a signal (pulse wave, breathing wave). Draws nothing until there's enough to draw. */
export function Trace({
  values,
  label,
  tone = "rr",
  fade = false,
  dot = false,
  className,
}: {
  values: number[];
  label: string;
  tone?: "hr" | "rr" | "spo2" | "sage" | "camera";
  fade?: boolean; // a soft fill beneath the line (on the camera only)
  dot?: boolean; // mark the newest sample
  className?: string;
}) {
  const W = 240;
  const H = 48;
  const pts = values.length >= 4 ? project(values, { width: W, height: H, pad: 5 }) : [];
  const last = pts.at(-1);
  return (
    <span className={twMerge(styles.trace, styles[tone], className)} role="img" aria-label={label}>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className={styles.traceSvg} aria-hidden>
        {fade && pts.length > 0 && <path className={styles.area} d={areaPath(pts, H)} />}
        {pts.length > 0 && <path className={styles.line} d={smoothPath(pts)} />}
      </svg>
      {/* the stretched SVG would squash a circle into an oval: the dot is placed in HTML instead */}
      {dot && last && <span className={styles.dot} style={{ left: `${(last[0] / W) * 100}%`, top: `${(last[1] / H) * 100}%` }} />}
    </span>
  );
}

/** Recent readings as thin rounded bars (newest on the right, in the series colour). Simulated readings are paler. */
export function Bars({
  values,
  label,
  tone = "hr",
  max = 28,
  className,
}: {
  values: { v: number; simulated?: boolean }[];
  label: string;
  tone?: "hr" | "rr" | "spo2" | "sage";
  max?: number;
  className?: string;
}) {
  const shown = values.slice(-max);
  if (shown.length < 2) return null;
  const vs = shown.map((p) => p.v);
  const lo = Math.min(...vs);
  const hi = Math.max(...vs);
  const span = hi - lo || 1;
  const H = 40;
  const gap = 240 / max;
  return (
    <svg viewBox={`0 0 240 ${H}`} preserveAspectRatio="none" className={twMerge(styles.bars, styles[tone], className)} role="img" aria-label={label}>
      {shown.map((p, i) => {
        const h = 8 + ((p.v - lo) / span) * (H - 10);
        const x = 240 - (shown.length - i) * gap + gap / 2;
        return <line key={i} x1={x} x2={x} y1={H - 1} y2={H - h} className={twMerge(styles.bar, i === shown.length - 1 && styles.barNow, p.simulated && styles.barSim)} />;
      })}
    </svg>
  );
}
