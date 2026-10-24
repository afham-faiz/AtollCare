// Network insights for operations leads: is the network accepting transfers quickly, where is load building, which
// hospitals are slow to respond — answered from Tiger Data continuous aggregates, with the storage and query cost
// shown beside the answers. Not a clinical screen: no patient is identifiable here.
"use client";

import { Database, Gauge, Loader2, Timer } from "lucide-react";
import { useState } from "react";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import Segmented from "@/app/components/(controls)/Segmented";
import Skeleton from "@/app/components/Skeleton";
import { api, type BenchmarkResponse, type InsightsResponse } from "@/lib/api";
import { fmtMin } from "@/lib/format";
import { useInsights } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./Insights.module.scss";

const SERIES = "#2579ce"; // categorical slot 1 (one series per chart — small multiples, no legend needed)
const GRID = "#eef2f6";
const AXIS = { fontSize: 12, fill: "#7d8e9e" };
const DAYS = ["7", "30", "60", "90"] as const;

const count = new Intl.NumberFormat("en-GB");
const day = (iso: string) => new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
const mb = (bytes?: number | null) => (bytes == null ? "—" : `${(bytes / 1024 / 1024).toFixed(1)} MB`);

function Stat({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div className={styles.stat}>
      <span className={styles.statLabel}>{label}</span>
      <span className={twMerge("tnum", styles.statValue)}>{value}</span>
      {detail && <span className={styles.statDetail}>{detail}</span>}
    </div>
  );
}

function ChartTooltip({ active, payload, label, unit }: { active?: boolean; payload?: { value: number }[]; label?: string; unit: string }) {
  if (!active || !payload?.length) return null;
  return (
    <div className={styles.tooltip}>
      <span className="text-ink-3">{label ? day(label) : ""}</span>
      <span className="tnum font-[600] text-ink">
        {count.format(payload[0].value)} {unit}
      </span>
    </div>
  );
}

function DailyChart({ data, field, unit, kind }: { data: InsightsResponse["daily"]; field: "transfers" | "alerts" | "questions"; unit: string; kind: "bar" | "area" }) {
  const rows = data.map((d) => ({ day: d.day, v: d[field] ?? 0 }));
  const common = { data: rows, margin: { top: 8, right: 4, bottom: 0, left: -24 } };
  const axes = (
    <>
      <CartesianGrid stroke={GRID} vertical={false} />
      <XAxis dataKey="day" tickFormatter={day} tick={AXIS} tickLine={false} axisLine={false} minTickGap={32} />
      <YAxis tick={AXIS} tickLine={false} axisLine={false} allowDecimals={false} width={48} />
      <Tooltip content={<ChartTooltip unit={unit} />} cursor={{ fill: "rgba(37,121,206,.06)", stroke: GRID }} />
    </>
  );
  return (
    <div className={styles.chart}>
      <ResponsiveContainer width="100%" height="100%">
        {kind === "bar" ? (
          <BarChart {...common} barCategoryGap={2}>
            {axes}
            <Bar dataKey="v" fill={SERIES} radius={[4, 4, 0, 0]} maxBarSize={24} isAnimationActive={false} />
          </BarChart>
        ) : (
          <AreaChart {...common}>
            {axes}
            <Area dataKey="v" stroke={SERIES} strokeWidth={2} fill={SERIES} fillOpacity={0.1} dot={false} activeDot={{ r: 4, stroke: "#fff", strokeWidth: 2 }} isAnimationActive={false} />
          </AreaChart>
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
          <p className={styles.eyebrow}>Operations</p>
          <h1 className={styles.title}>Network insights</h1>
          <p className={styles.lede}>How quickly the transfer network responds, and where load is building.</p>
        </div>
        <Segmented label="Period" value={days} onChange={(v) => { setDays(v); setBench(null); }} options={DAYS.map((d) => ({ value: d, label: `${d} days` }))} />
      </header>

      {!data ? (
        <div className="flex flex-col gap-[1rem]">
          <Skeleton className="h-[6.5rem] rounded-[1.25rem]" />
          <Skeleton className="h-[16rem] rounded-[1.25rem]" />
        </div>
      ) : !data.available ? (
        <section className={styles.unavailable}>
          <Database size={22} className="text-ink-3" />
          <h2 className="text-[1.125rem] font-[600]">Network insights run on Tiger Data</h2>
          <p className="max-w-[34rem] text-ink-2">{data.reason}</p>
          <p className="text-[0.875rem] text-ink-3">Currently connected to: {data.database}. Clinical screens work without it.</p>
        </section>
      ) : (
        <>
          {data.seeded_transfers > 0 && (
            <p className={styles.notice}>
              Includes <strong className="tnum">{count.format(data.seeded_transfers)}</strong> transfers of seeded demo history (simulated) alongside{" "}
              <strong className="tnum">{count.format(data.live_transfers)}</strong> live {data.live_transfers === 1 ? "transfer" : "transfers"}.
            </p>
          )}

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

              <section className={styles.card}>
                <h2 className={styles.cardTitle}>Transfers per day</h2>
                <DailyChart data={data.daily} field="transfers" unit="transfers" kind="bar" />
              </section>

              <div className={styles.pair}>
                <section className={styles.card}>
                  <h2 className={styles.cardTitle}>Deterioration alerts per day</h2>
                  <DailyChart data={data.daily} field="alerts" unit="alerts" kind="area" />
                </section>
                <section className={styles.card}>
                  <h2 className={styles.cardTitle}>Questions from hospitals per day</h2>
                  <DailyChart data={data.daily} field="questions" unit="questions" kind="area" />
                </section>
              </div>
              <button type="button" className={styles.disclosure} onClick={() => setShowTable((v) => !v)} aria-expanded={showTable}>
                {showTable ? "Hide" : "Show"} daily figures as a table
              </button>
              {showTable && (
                <div className={twMerge(styles.card, styles.tableWrap)}>
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

              <section className={styles.card}>
                <h2 className={styles.cardTitle}>Time to acceptance by receiving hospital</h2>
                <ul className={styles.hospitals}>
                  {data.destinations.map((d) => {
                    const max = Math.max(...data.destinations.map((x) => x.median_min_to_accept ?? 0), 1);
                    return (
                      <li key={d.destination_id}>
                        <span className="min-w-0 truncate font-[550]">{d.name}</span>
                        <span className="tnum text-[0.875rem] text-ink-3">{count.format(d.transfers)} transfers</span>
                        <span className={styles.meter} aria-hidden>
                          <span style={{ width: `${((d.median_min_to_accept ?? 0) / max) * 100}%` }} />
                        </span>
                        <span className="tnum w-[4.5rem] text-right font-[600]">{d.median_min_to_accept != null ? `${d.median_min_to_accept} min` : "—"}</span>
                      </li>
                    );
                  })}
                </ul>
              </section>
            </>
          ) : (
            <section className={styles.unavailable}>
              <h2 className="text-[1.125rem] font-[600]">No transfers in the last {days} days</h2>
              <p className="text-ink-2">Run a few transfers, or seed demo history from the presenter panel (Ctrl + .).</p>
            </section>
          )}

          {/* the proof: what Tiger Data is doing underneath these answers */}
          <section className={twMerge(styles.card, styles.engine)}>
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
                    <p className="font-mono text-[0.8125rem] text-ink-2">{s.name}</p>
                    <p className="tnum text-[1.375rem] font-[600] tracking-[-0.02em]">{count.format(s.rows)} rows</p>
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
                  <Timer size={15} /> Queries behind this page
                </p>
                <ul className={styles.queries}>
                  {data.queries.map((q) => (
                    <li key={q.name}>
                      <span className="min-w-0">
                        <span className="block font-[550]">{q.name}</span>
                        <span className="block truncate text-[0.8125rem] text-ink-3">{q.source}</span>
                      </span>
                      <span className="tnum font-[600]">{q.ms} ms</span>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <p className={styles.subhead}>
                  <Gauge size={15} /> Continuous aggregate vs raw scan
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
                        <span className="tnum text-[0.875rem] font-[600]">{b.ms} ms</span>
                      </div>
                    ))}
                    <p className="tnum font-[600]">{bench.speedup}× faster from the aggregate · median of 3 runs</p>
                  </div>
                ) : (
                  <p className="text-[0.875rem] text-ink-2">Ask the same question of the aggregate and of every raw reading, timed live.</p>
                )}
                <ButtonBase size="sm" className="mt-[.75rem]" onClick={runBenchmark} disabled={benching}>
                  {benching ? <Loader2 size={15} className="animate-spin" /> : <Gauge size={15} />} {bench ? "Run again" : "Run the benchmark"}
                </ButtonBase>
              </div>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
