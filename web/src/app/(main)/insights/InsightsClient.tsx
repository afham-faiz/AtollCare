// Network insights for operations leads: is the network accepting transfers quickly, where is load building, which
// hospitals are slow to respond — answered from Tiger Data continuous aggregates, with the storage and query cost
// shown beside the answers. Not a clinical screen: no patient is identifiable here.
"use client";

import { Database, Gauge, Loader2, Timer } from "lucide-react";
import { useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import Segmented from "@/app/components/(controls)/Segmented";
import Skeleton from "@/app/components/Skeleton";
import { api, type BenchmarkResponse, type InsightsResponse } from "@/lib/api";
import { fmtMin } from "@/lib/format";
import { CHART, PALETTE } from "@/lib/palette";
import { useInsights } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./Insights.module.scss";

// one series per chart (small multiples, no legend): thin sage bars with the latest day in deep sage; daily counts
// elsewhere are steps, never smoothed curves (a curve would invent values between days)
const LINE: Record<"alerts" | "questions", string> = { alerts: PALETTE.caution, questions: PALETTE.blue500 };
const DAYS = ["7", "30", "60", "90"] as const;

const count = new Intl.NumberFormat("en-GB");
const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const mb = (bytes?: number | null) => (bytes == null ? "—" : `${(bytes / 1024 / 1024).toFixed(1)} MB`);

function Stat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={twMerge("numeral", styles.statValue)}>{value}</span>
      {detail && <span className={styles.statDetail}>{detail}</span>}
    </div>
  );
}

function ChartTooltip({ active, payload, label, unit }: { active?: boolean; payload?: { value: number }[]; label?: string; unit: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <span className="text-ink-3">{label ? day(label) : ""}</span>
      <span className="tnum font-[500] text-ink">
        {count.format(payload[0].value)} {unit}
      </span>
    </div>
  );
}

function DailyChart({ data, field, unit, kind }: { data: InsightsResponse["daily"]; field: "transfers" | "alerts" | "questions"; unit: string; kind: "bar" | "line" }) {
  const rows = data.map((d) => ({ day: d.day, v: d[field] ?? 0 }));
  const avg = rows.length ? rows.reduce((n, r) => n + r.v, 0) / rows.length : 0;
  const common = { data: rows, margin: { top: 8, right: 4, bottom: 0, left: -24 } };
  const axes = (
    <>
      <CartesianGrid {...CHART.grid} />
      <XAxis dataKey="day" tickFormatter={day} tick={CHART.tick} tickLine={false} axisLine={false} minTickGap={40} />
      <YAxis tick={CHART.tick} tickLine={false} axisLine={false} allowDecimals={false} width={48} tickCount={3} />
    </>
  );
  return (
    <div className={styles.chart}>
      <ResponsiveContainer width="100%" height="100%">
        {kind === "bar" ? (
          <BarChart {...common} barCategoryGap="30%">
            {axes}
            <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: PALETTE.line }} />
            <ReferenceLine y={avg} stroke={PALETTE.ink4} strokeDasharray="2 4" ifOverflow="extendDomain" />
            <Bar dataKey="v" radius={[999, 999, 999, 999]} maxBarSize={6} isAnimationActive={false}>
              {rows.map((r, i) => (
                <Cell key={r.day} fill={i === rows.length - 1 ? PALETTE.sage700 : PALETTE.sage300} />
              ))}
            </Bar>
          </BarChart>
        ) : (
          <LineChart {...common}>
            {axes}
            <Tooltip content={<ChartTooltip unit={unit} />} cursor={CHART.cursor} />
            <Line dataKey="v" type="stepAfter" stroke={LINE[field as "alerts" | "questions"]} strokeWidth={1.5} dot={false} activeDot={{ r: 4, stroke: PALETTE.white, strokeWidth: 2 }} isAnimationActive={false} />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

export default function () {
  const [days, setDays] = useState<(typeof DAYS)[number]>("30");
  const { data } = useInsights(Number(days));
  const [bench, setBench] = useState<BenchmarkResponse | null>(null);
  const [benching, setBenching] = useState(false);
  const [showTable, setShowTable] = useState(false);

  const runBenchmark = async () => {
    setBenching(true);
    try {
      setBench(await api<BenchmarkResponse>(`/insights/benchmark?days=${days}`));
    } catch (err) {
      toastError(err);
    } finally {
      setBenching(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <div className="min-w-0">
          <h1 className={styles.title}>Network insights</h1>
          <p className={styles.lede}>How quickly the transfer network responds, and where load is building.</p>
          {data?.available && data.seeded_transfers > 0 && (
            <p className={styles.notice}>
              Includes {count.format(data.seeded_transfers)} transfers of seeded demo history alongside {count.format(data.live_transfers)} live{" "}
              {data.live_transfers === 1 ? "transfer" : "transfers"}.
            </p>
          )}
        </div>
        <Segmented label="Period" value={days} onChange={(v) => { setDays(v); setBench(null); }} options={DAYS.map((d) => ({ value: d, label: `${d} days` }))} />
      </header>

      {!data ? (
        <div className="flex flex-col gap-[1rem]">
          <Skeleton className="h-[6.5rem] rounded-[1.75rem]" />
          <Skeleton className="h-[16rem] rounded-[1.75rem]" />
        </div>
      ) : !data.available ? (
        <section className={styles.unavailable}>
          <Database size={22} strokeWidth={1.75} className="text-ink-3" />
          <h2 className="text-[1.25rem]">Network insights run on Tiger Data</h2>
          <p className="max-w-[34rem] text-ink-2">{data.reason}</p>
          <p className="text-[0.875rem] text-ink-3">Currently connected to: {data.database}. Clinical screens work without it.</p>
        </section>
      ) : (
        <>
          {data.kpis && data.kpis.transfers > 0 ? (
            <>
              <div className={styles.stats}>
                <Stat label="Transfers handed off" value={count.format(data.kpis.handed_off)} detail={`${count.format(data.kpis.accepted)} accepted`} />
                <Stat
                  label="Median time to acceptance"
                  value={data.kpis.median_min_to_accept != null ? `${data.kpis.median_min_to_accept} min` : "—"}
                  detail={data.kpis.p90_min_to_accept != null ? `9 in 10 within ${data.kpis.p90_min_to_accept} min` : undefined}
                />
                <Stat label="Median journey" value={data.kpis.median_journey_min != null ? fmtMin(data.kpis.median_journey_min) : "—"} detail="departure to arrival" />
                <Stat label="High risk at last score" value={count.format(data.kpis.high_risk)} detail="NEWS2 7 or more" />
              </div>

              <section className={twMerge("card", styles.card)}>
                <h2 className={styles.cardTitle}>Transfers per day</h2>
                <DailyChart data={data.daily} field="transfers" unit="transfers" kind="bar" />
              </section>

              <div className={styles.pair}>
                <section className={twMerge("card", styles.card)}>
                  <h2 className={styles.cardTitle}>Deterioration alerts per day</h2>
                  <DailyChart data={data.daily} field="alerts" unit="alerts" kind="line" />
                </section>
                <section className={twMerge("card", styles.card)}>
                  <h2 className={styles.cardTitle}>Questions from hospitals per day</h2>
                  <DailyChart data={data.daily} field="questions" unit="questions" kind="line" />
                </section>
              </div>
              <button type="button" className={styles.disclosure} onClick={() => setShowTable((v) => !v)} aria-expanded={showTable}>
                {showTable ? "Hide" : "Show"} daily figures as a table
              </button>
              {showTable && (
                <div className={twMerge("card", styles.card, styles.tableWrap)}>
                  <table className={styles.table}>
                    <thead>
                      <tr>
                        <th>Day</th>
                        <th>Transfers</th>
                        <th>Alerts</th>
                        <th>Questions</th>
                        <th>Vitals readings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...data.daily].reverse().map((d) => (
                        <tr key={d.day}>
                          <td>{day(d.day)}</td>
                          <td className="tnum">{d.transfers}</td>
                          <td className="tnum">{d.alerts}</td>
                          <td className="tnum">{d.questions}</td>
                          <td className="tnum">{count.format(d.readings)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              <section className={twMerge("card", styles.card)}>
                <h2 className={styles.cardTitle}>Time to acceptance by receiving hospital</h2>
                <ul className={styles.hospitals}>
                  {data.destinations.map((d) => {
                    const max = Math.max(...data.destinations.map((x) => x.median_min_to_accept ?? 0), 1);
                    return (
                      <li key={d.destination_id}>
                        <span className="min-w-0 truncate font-[500]">{d.name}</span>
                        <span className="tnum text-[0.875rem] text-ink-3">{count.format(d.transfers)} transfers</span>
                        <span className={styles.meter} aria-hidden>
                          <span style={{ width: `${((d.median_min_to_accept ?? 0) / max) * 100}%` }} />
                        </span>
                        <span className="tnum w-[4.5rem] text-right font-[500]">{d.median_min_to_accept != null ? `${d.median_min_to_accept} min` : "—"}</span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            </>
          ) : (
            <section className={styles.unavailable}>
              <h2 className="text-[1.25rem]">No transfers in the last {days} days</h2>
              <p className="text-ink-2">Run a few transfers, or seed demo history from the presenter panel (Ctrl + .).</p>
            </section>
          )}

          {/* the proof: what Tiger Data is doing underneath these answers */}
          <section className={twMerge("card", styles.card, styles.engine)}>
            <div className={styles.engineHead}>
              <div>
                <h2 className={styles.cardTitle}>Built on {data.database}</h2>
                <p className="text-[0.875rem] text-ink-2">
                  TimescaleDB {data.database_version} · {data.storage.length} hypertables · {data.aggregates.length} continuous aggregates (
                  {data.aggregates.join(", ")})
                </p>
              </div>
            </div>

            <div className={styles.tables}>
              {data.storage.map((s) => {
                const saved = s.bytes_before_compression && s.bytes_after_compression ? 1 - s.bytes_after_compression / s.bytes_before_compression : null;
                return (
                  <div key={s.name} className={styles.tableStat}>
                    <p className="mono text-[0.8125rem] text-ink-3">{s.name}</p>
                    <p>
                      <span className="numeral text-[2rem]">{count.format(s.rows)}</span> <span className="unit">rows</span>
                    </p>
                    <p className="tnum text-[0.8125rem] text-ink-3">
                      {s.compressed_chunks} of {s.chunks} daily chunks compressed (older than 7 days)
                    </p>
                    {saved != null && (
                      <>
                        <span className={styles.meter} aria-hidden>
                          <span style={{ width: `${saved * 100}%` }} />
                        </span>
                        <p className="tnum text-[0.8125rem] text-ink-2">
                          Those chunks: {mb(s.bytes_before_compression)} → {mb(s.bytes_after_compression)} ({Math.round(saved * 100)}% smaller)
                        </p>
                      </>
                    )}
                  </div>
                );
              })}
            </div>

            <div className={styles.engineGrid}>
              <div>
                <p className={styles.subhead}>
                  <Timer size={15} strokeWidth={1.75} /> Queries behind this page
                </p>
                <ul className={styles.queries}>
                  {data.queries.map((q) => (
                    <li key={q.name}>
                      <span className="min-w-0">
                        <span className="block font-[500]">{q.name}</span>
                        <span className="block truncate text-[0.8125rem] text-ink-3">{q.source}</span>
                      </span>
                      <span className="tnum shrink-0 font-[500] whitespace-nowrap">{q.ms} ms</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className={styles.subhead}>
                  <Gauge size={15} strokeWidth={1.75} /> Continuous aggregate vs raw scan
                </p>
                {bench ? (
                  <div className={styles.bench}>
                    <p className="text-[0.875rem] text-ink-2">{bench.question}</p>
                    {[
                      { label: "Continuous aggregate", ms: bench.aggregate_ms, main: true },
                      { label: `Raw hypertable · ${count.format(bench.rows_scanned)} rows`, ms: bench.raw_ms, main: false },
                    ].map((b) => (
                      <div key={b.label} className={styles.benchRow}>
                        <span className="text-[0.8125rem] text-ink-2">{b.label}</span>
                        <span className={twMerge(styles.benchBar, !b.main && styles.benchBarMuted)} style={{ width: `${Math.max(2, (b.ms / Math.max(bench.raw_ms, bench.aggregate_ms)) * 100)}%` }} />
                        <span className="tnum text-[0.875rem] font-[500]">{b.ms} ms</span>
                      </div>
                    ))}
                    <p className="tnum font-[500]">{bench.speedup}× faster from the aggregate · median of 3 runs</p>
                  </div>
                ) : (
                  <p className="text-[0.875rem] text-ink-2">Ask the same question of the aggregate and of every raw reading, timed live.</p>
                )}
                <ButtonBase size="sm" className="mt-[.75rem]" onClick={runBenchmark} disabled={benching}>
                  {benching ? <Loader2 size={15} strokeWidth={1.75} className="animate-spin" /> : <Gauge size={15} strokeWidth={1.75} />} {bench ? "Run again" : "Run the benchmark"}
                </ButtonBase>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
