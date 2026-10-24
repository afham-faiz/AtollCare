// Understated trend of real recorded readings. Demo-signal segments are drawn dashed so they never pass as measured.
import type { Point } from "@/lib/clinical";

export default function ({
  points,
  color = "currentColor",
  className,
  height = 36,
}: {
  points: Point[];
  color?: string;
  className?: string;
  height?: number;
}) {
  if (points.length < 3) return null;
  const w = 120;
  const h = height;
  const t0 = points[0].t;
  const t1 = points[points.length - 1].t || t0 + 1;
  const vs = points.map((p) => p.v);
  const lo = Math.min(...vs);
  const hi = Math.max(...vs);
  const pad = Math.max(2, (hi - lo) * 0.2);
  const x = (t: number) => ((t - t0) / Math.max(1, t1 - t0)) * w;
  const y = (v: number) => h - 3 - ((v - (lo - pad)) / (hi + pad - (lo - pad))) * (h - 6);

  // split into runs of the same source so simulated runs can be styled differently
  const runs: Point[][] = [];
  for (const p of points) {
    const run = runs[runs.length - 1];
    if (run && run[run.length - 1].source === p.source) run.push(p);
    else runs.push(run ? [run[run.length - 1], p] : [p]); // start each run at the previous point so the line stays continuous
  }
  const last = points[points.length - 1];
  return (
    <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className={className} aria-hidden>
      {runs.map((run, i) => (
        <polyline
          key={i}
          points={run.map((p) => `${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join(" ")}
          fill="none"
          stroke={color}
          strokeWidth={1.75}
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeDasharray={run[run.length - 1].source === "simulated" ? "3 3" : undefined}
          vectorEffect="non-scaling-stroke"
          opacity={run[run.length - 1].source === "simulated" ? 0.55 : 1}
        />
      ))}
      <circle cx={x(last.t)} cy={y(last.v)} r={2.5} fill={color} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
