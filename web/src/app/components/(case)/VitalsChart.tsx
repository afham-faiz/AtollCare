// F-M3.2 / F-M2.6 Vitals trend (Tiger Data 1-min buckets) + hedged deterioration forecast.
"use client";

import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import Card from "@/app/components/Card";
import PillBase from "@/app/components/(pills)/PillBase";
import type { DeteriorationForecast, TrendResponse } from "@/lib/api";
import { fmtMin, fmtTime } from "@/lib/format";

export function ForecastNote({ forecast }: { forecast?: DeteriorationForecast | null }) {
  if (!forecast) return <p className="text-[0.875rem] text-muted">Trend needs at least 3 one-minute buckets.</p>;
  return (
    <p className="text-[0.875rem]">
      Trend suggests NEWS2 is <strong>{forecast.trend}</strong> ({forecast.slope_per_hour > 0 ? "+" : ""}
      {forecast.slope_per_hour}/h, {forecast.points_used} points, {forecast.confidence} confidence)
      {forecast.projected_news2_at_arrival !== null && forecast.projected_news2_at_arrival !== undefined && (
        <>
          {" "}— projected ≈ {forecast.projected_news2_at_arrival} over the next {fmtMin(forecast.horizon_min)}
        </>
      )}
      {forecast.minutes_to_news2_7 !== null && forecast.minutes_to_news2_7 !== undefined && forecast.minutes_to_news2_7 > 0 && (
        <> · may reach 7 in ~{fmtMin(forecast.minutes_to_news2_7)}</>
      )}
      .
    </p>
  );
}

export default function ({ trend, className }: { trend?: TrendResponse; className?: string }) {
  const data = (trend?.buckets ?? []).map((b) => ({
    t: fmtTime(b.t),
    HR: b.hr ? Math.round(b.hr) : null,
    RR: b.rr ? Math.round(b.rr) : null,
    "SpO₂": b.spo2 ? Math.round(b.spo2) : null,
    NEWS2: b.news2,
  }));
  const fc = trend?.forecast;
  if (fc && data.length && fc.projected_news2_at_arrival !== null && fc.projected_news2_at_arrival !== undefined) {
    const last = data[data.length - 1];
    data[data.length - 1] = { ...last, Forecast: last.NEWS2 } as typeof last;
    data.push({ t: `+${fmtMin(fc.horizon_min)}`, HR: null, RR: null, "SpO₂": null, NEWS2: null, Forecast: fc.projected_news2_at_arrival } as typeof last);
  }
  return (
    <Card
      title="Vitals trend"
      className={className}
      aside={trend && <PillBase className="text-[0.875rem] text-muted">Tiger Data · {trend.source}</PillBase>}
    >
      {data.length === 0 ? (
        <p className="text-muted">No vitals recorded yet.</p>
      ) : (
        <div className="h-[14rem] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="t" tick={{ fontSize: 14, fill: "var(--muted)" }} />
              <YAxis yAxisId="v" tick={{ fontSize: 14, fill: "var(--muted)" }} />
              <YAxis yAxisId="n" orientation="right" domain={[0, 20]} tick={{ fontSize: 14, fill: "var(--muted)" }} />
              <Tooltip contentStyle={{ background: "var(--raised)", border: "1px solid var(--border)", fontSize: 14 }} />
              <Legend wrapperStyle={{ fontSize: 14 }} />
              <Line yAxisId="v" dataKey="HR" stroke="#d92d20" dot={false} connectNulls strokeWidth={2} />
              <Line yAxisId="v" dataKey="RR" stroke="#0e7c86" dot={false} connectNulls strokeWidth={2} />
              <Line yAxisId="v" dataKey="SpO₂" stroke="#6b4fbb" dot={false} connectNulls strokeWidth={2} />
              <Line yAxisId="n" dataKey="NEWS2" stroke="#f79009" dot connectNulls strokeWidth={2} />
              <Line yAxisId="n" dataKey="Forecast" stroke="#f79009" strokeDasharray="5 4" dot={false} connectNulls />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-[.5rem]">
        <ForecastNote forecast={fc} />
      </div>
    </Card>
  );
}
