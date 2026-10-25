// Vitals trend from recorded readings (Tiger Data 1-minute aggregate) with a hedged, dashed NEWS2 projection.
"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TrendResponse } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { CHART, PALETTE } from "@/lib/palette";

// bedside-monitor colours; NEWS2 in ink, as a step line (it changes in steps, not smoothly)
const SERIES = [
  { key: "HR", color: PALETTE.seriesHr, axis: "v", label: "Heart rate", step: false },
  { key: "RR", color: PALETTE.seriesRr, axis: "v", label: "Breathing", step: false },
  { key: "SpO₂", color: PALETTE.seriesSpo2, axis: "v", label: "SpO₂", step: false },
  { key: "NEWS2", color: PALETTE.ink, axis: "n", label: "NEWS2", step: true },
];

type Row = { t: string; HR?: number | null; RR?: number | null; "SpO₂"?: number | null; NEWS2?: number | null };

export default function ({ trend, tz, className }: { trend?: TrendResponse; tz?: string; className?: string }) {
  const data: Row[] = (trend?.buckets ?? []).map((b) => ({
    t: fmtTime(b.t, tz),
    HR: b.hr ? Math.round(b.hr) : null,
    RR: b.rr ? Math.round(b.rr) : null,
    "SpO₂": b.spo2 ? Math.round(b.spo2) : null,
    NEWS2: b.news2,
  }));
  // a straight line through a few noisy points says which way, not where or when: the direction only, no projection
  const fc = trend?.forecast;
  return (
    <div className={className}>
      <div className="mb-[1rem] flex flex-wrap gap-x-[1.25rem] gap-y-[.25rem] text-[0.8125rem] text-ink-3">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-[.5rem]">
            <span className="h-[.5rem] w-[.5rem] rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      {data.length < 2 ? (
        <p className="py-[2rem] text-center text-ink-3">The trend appears after a few minutes of measured readings (Presage or crew).</p>
      ) : (
        <div className="h-[13rem] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
              <CartesianGrid {...CHART.grid} />
              <XAxis dataKey="t" tick={CHART.tick} tickLine={false} axisLine={false} minTickGap={36} />
              <YAxis yAxisId="v" tick={CHART.tick} tickLine={false} axisLine={false} domain={["auto", "auto"]} tickCount={3} />
              <YAxis yAxisId="n" orientation="right" domain={[0, 20]} hide />
              <Tooltip contentStyle={CHART.tooltip} cursor={CHART.cursor} />
              {SERIES.map((s) => (
                <Line
                  key={s.key}
                  yAxisId={s.axis}
                  dataKey={s.key}
                  type={s.step ? "stepAfter" : "monotone"}
                  stroke={s.color}
                  strokeWidth={1.5}
                  dot={false}
                  activeDot={{ r: 4, stroke: PALETTE.white, strokeWidth: 2 }}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {trend && (
        <p className="mt-[.5rem] text-[0.8125rem] text-ink-3">
          Measured readings only ·{" "}
          {trend.source === "vitals_1m"
            ? `Tiger Data continuous aggregate vitals_1m${trend.query_ms != null ? `, ${trend.query_ms} ms` : ""}`
            : trend.source === "raw"
              ? "raw readings (TimescaleDB not available)"
              : "in-memory demo store"}
        </p>
      )}
      {fc && (
        <p className="mt-[.75rem] text-[0.875rem] text-ink-2">
          NEWS2 is <span className="font-[500] text-ink">{fc.trend}</span>.{" "}
          <span className="text-ink-3">
            {fc.points_used} one-minute points, {fc.confidence} confidence.
          </span>
        </p>
      )}
    </div>
  );
}
