// Vitals trend from recorded readings (Tiger Data 1-minute aggregate) with a hedged, dashed NEWS2 projection.
"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { TrendResponse } from "@/lib/api";
import { fmtMin, fmtTime } from "@/lib/format";

const SERIES = [
  { key: "HR", color: "#c8322a", axis: "v", label: "Heart rate" },
  { key: "RR", color: "#0f9286", axis: "v", label: "Respiration" },
  { key: "SpO₂", color: "#2579ce", axis: "v", label: "SpO₂" },
  { key: "NEWS2", color: "#a8620a", axis: "n", label: "NEWS2" },
];

type Row = { t: string; HR?: number | null; RR?: number | null; "SpO₂"?: number | null; NEWS2?: number | null; Projection?: number | null };

export default function ({ trend, tz, className }: { trend?: TrendResponse; tz?: string; className?: string }) {
  const data: Row[] = (trend?.buckets ?? []).map((b) => ({
    t: fmtTime(b.t, tz),
    HR: b.hr ? Math.round(b.hr) : null,
    RR: b.rr ? Math.round(b.rr) : null,
    "SpO₂": b.spo2 ? Math.round(b.spo2) : null,
    NEWS2: b.news2,
  }));
  const fc = trend?.forecast;
  if (fc && data.length && fc.projected_news2_at_arrival != null && fc.horizon_min) {
    data[data.length - 1] = { ...data[data.length - 1], Projection: data[data.length - 1].NEWS2 };
    data.push({ t: `+${fmtMin(fc.horizon_min)}`, Projection: fc.projected_news2_at_arrival });
  }
  return (
    <div className={className}>
      <div className="mb-[.75rem] flex flex-wrap gap-x-[1rem] gap-y-[.25rem] text-[0.8125rem] text-ink-2">
        {SERIES.map((s) => (
          <span key={s.key} className="flex items-center gap-[.375rem]">
            <span className="h-[.125rem] w-[.875rem] rounded-full" style={{ background: s.color }} />
            {s.label}
          </span>
        ))}
      </div>
      {data.length < 2 ? (
        <p className="py-[2rem] text-center text-ink-3">The trend appears after a few minutes of measured readings (Presage or crew).</p>
      ) : (
        <div className="h-[12rem] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -22 }}>
              <CartesianGrid stroke="#eef2f6" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 12, fill: "#8a9aaa" }} tickLine={false} axisLine={false} minTickGap={28} />
              <YAxis yAxisId="v" tick={{ fontSize: 12, fill: "#8a9aaa" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <YAxis yAxisId="n" orientation="right" domain={[0, 20]} hide />
              <Tooltip contentStyle={{ borderRadius: 12, border: "1px solid #e7edf2", fontSize: 13, boxShadow: "0 8px 24px -8px rgba(23,42,58,.15)" }} />
              {SERIES.map((s) => (
                <Line key={s.key} yAxisId={s.axis} dataKey={s.key} stroke={s.color} strokeWidth={1.75} dot={false} connectNulls isAnimationActive={false} />
              ))}
              <Line yAxisId="n" dataKey="Projection" stroke="#a8620a" strokeWidth={1.5} strokeDasharray="4 4" dot={false} connectNulls isAnimationActive={false} />
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
          Trend suggests NEWS2 is <span className="font-[600] text-ink">{fc.trend}</span>
          {fc.projected_news2_at_arrival != null && fc.horizon_min ? <> — around {fc.projected_news2_at_arrival} in {fmtMin(fc.horizon_min)}</> : null}.{" "}
          <span className="text-ink-3">
            {fc.points_used} one-minute points, {fc.confidence} confidence.
          </span>
        </p>
      )}
    </div>
  );
}
