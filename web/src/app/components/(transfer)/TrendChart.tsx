// Vitals trend from the Tiger Data 1-minute continuous aggregate, with a hedged NEWS2 forecast line.
"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import Card from "@/app/components/Card";
import type { TrendResponse } from "@/lib/api";
import { fmtMin, fmtTime } from "@/lib/format";

const SERIES = [
  { key: "HR", color: "#d92d20", axis: "v" },
  { key: "RR", color: "#0e7c86", axis: "v" },
  { key: "SpO₂", color: "#2563c9", axis: "v" },
  { key: "NEWS2", color: "#c76a00", axis: "n" },
];

export default function ({ trend, tz, className }: { trend?: TrendResponse; tz?: string; className?: string }) {
  type Row = { t: string; HR?: number | null; RR?: number | null; "SpO₂"?: number | null; NEWS2?: number | null; Forecast?: number | null };
  const data: Row[] = (trend?.buckets ?? []).map((b) => ({
    t: fmtTime(b.t, tz),
    HR: b.hr ? Math.round(b.hr) : null,
    RR: b.rr ? Math.round(b.rr) : null,
    "SpO₂": b.spo2 ? Math.round(b.spo2) : null,
    NEWS2: b.news2,
  }));
  const fc = trend?.forecast;
  if (fc && data.length && fc.projected_news2_at_arrival != null && fc.horizon_min) {
    data[data.length - 1] = { ...data[data.length - 1], Forecast: data[data.length - 1].NEWS2 };
    data.push({ t: `+${fmtMin(fc.horizon_min)}`, Forecast: fc.projected_news2_at_arrival });
  }
  return (
    <Card
      className={className}
      title="Trend"
      aside={
        <span className="flex flex-wrap gap-x-[.75rem] text-[0.875rem] text-muted">
          {SERIES.map((s) => (
            <span key={s.key} className="flex items-center gap-[.25rem]">
              <span className="h-[.5rem] w-[.75rem] rounded-[.125rem]" style={{ background: s.color }} />
              {s.key}
            </span>
          ))}
        </span>
      }
    >
      {data.length === 0 ? (
        <p className="text-muted">Waiting for readings…</p>
      ) : (
        <div className="h-[13rem] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 6, right: 4, bottom: 0, left: -18 }}>
              <CartesianGrid stroke="#e1e7eb" vertical={false} />
              <XAxis dataKey="t" tick={{ fontSize: 14, fill: "#8a979f" }} tickLine={false} axisLine={false} minTickGap={24} />
              <YAxis yAxisId="v" tick={{ fontSize: 14, fill: "#8a979f" }} tickLine={false} axisLine={false} domain={["auto", "auto"]} />
              <YAxis yAxisId="n" orientation="right" domain={[0, 20]} hide />
              <Tooltip contentStyle={{ borderRadius: 8, border: "1px solid #e1e7eb", fontSize: 14 }} />
              {SERIES.map((s) => (
                <Line
                  key={s.key}
                  yAxisId={s.axis}
                  dataKey={s.key}
                  stroke={s.color}
                  strokeWidth={2}
                  dot={false}
                  connectNulls
                  isAnimationActive={false}
                />
              ))}
              <Line yAxisId="n" dataKey="Forecast" stroke="#c76a00" strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {fc && (
        <p className="mt-[.5rem] text-[0.875rem] text-muted">
          Trend suggests NEWS2 is <strong className="text-fg">{fc.trend}</strong>
          {fc.projected_news2_at_arrival != null && fc.horizon_min ? (
            <> — about {fc.projected_news2_at_arrival} in {fmtMin(fc.horizon_min)}</>
          ) : null}{" "}
          ({fc.points_used} one-minute points, {fc.confidence} confidence).
        </p>
      )}
    </Card>
  );
}
