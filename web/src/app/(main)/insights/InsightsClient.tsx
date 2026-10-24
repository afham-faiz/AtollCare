// Network insights: how much warning receiving teams get, across every completed transfer in the region.
// Served from the transfer_log hypertable and its daily continuous aggregate (Tiger Data).
"use client";

import { Database, Loader2 } from "lucide-react";
import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import Segmented from "@/app/components/(controls)/Segmented";
import PillBase from "@/app/components/(pills)/PillBase";
import Skeleton from "@/app/components/Skeleton";
import { post, type InsightsGroup, type InsightsResponse, type SeedResponse } from "@/lib/api";
import { MODE_LABEL, fmtMin, place } from "@/lib/format";
import { useInsights, useMeta } from "@/lib/swr";
import { toast, toastError } from "@/lib/toast";

const WINDOWS = ["30", "60", "90"] as const;
const RADIO = "#9aa9b6";
const ATOLLCARE = "#0f9286";
const WARNING = "#2579ce";

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-col gap-[.25rem] rounded-[1rem] border-[1px] border-line bg-surface p-[1.125rem]">
      <span className="text-[0.8125rem] font-[550] text-ink-3">{label}</span>
      <span className="text-[1.75rem] font-[650] tracking-[-0.02em] tabular-nums">{value}</span>
      {note && <span className="text-[0.8125rem] text-ink-2">{note}</span>}
    </div>
  );
}

function Card({ title, aside, children, className }: { title: string; aside?: React.ReactNode; children: React.ReactNode; className?: string }) {
  return (
    <section className={twMerge("rounded-[1rem] border-[1px] border-line bg-surface p-[1.25rem]", className)}>
      <header className="mb-[1rem] flex flex-wrap items-baseline justify-between gap-[.5rem]">
        <h2 className="text-[1rem] font-[650]">{title}</h2>
        {aside}
      </header>
      {children}
    </section>
  );
}

function GroupTable({ rows, label, metric }: { rows: InsightsGroup[]; label: (k: string) => string; metric: "journey" | "accept" }) {
  return (
    <table className="w-full text-[0.875rem]">
      <thead className="text-left text-[0.8125rem] text-ink-3">
        <tr>
          <th className="pb-[.5rem] font-[550]" />
          <th className="pb-[.5rem] text-right font-[550]">Transfers</th>
          <th className="pb-[.5rem] text-right font-[550]">{metric === "journey" ? "Median journey" : "Median to accept"}</th>
          <th className="pb-[.5rem] text-right font-[550]">Median warning</th>
        </tr>
      </thead>
      <tbody className="tabular-nums">
        {rows.map((r) => (
          <tr key={r.key} className="border-t-[1px] border-line">
            <td className="py-[.5rem] font-[550]">{label(r.key)}</td>
            <td className="py-[.5rem] text-right">{r.transfers}</td>
            <td className="py-[.5rem] text-right">{fmtMin(metric === "journey" ? r.median_journey_min : r.median_accept_min)}</td>
            <td className="py-[.5rem] text-right">{fmtMin(r.median_warning_min)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Empty({ onSeed, busy }: { onSeed: () => void; busy: boolean }) {
  return (
    <div className="flex flex-col items-start gap-[.75rem] rounded-[1rem] border-[1px] border-dashed border-line-strong p-[2rem]">
      <h2 className="text-[1.125rem] font-[650]">No completed transfers in this window yet</h2>
      <p className="max-w-[36rem] text-ink-2">
        Every transfer that arrives is logged here. For the demo, seed 60 days of synthetic history: a radio/phone baseline
        followed by AtollCare handoffs. It is flagged as synthetic everywhere.
      </p>
      <ButtonPrimary size="sm" onClick={onSeed} disabled={busy}>
        {busy ? <Loader2 size={15} className="animate-spin" /> : <Database size={15} />} Seed 60 days of history
      </ButtonPrimary>
    </div>
  );
}

function Body({ data }: { data: InsightsResponse }) {
  const { data: meta } = useMeta();
  const region = meta?.regions.find((r) => r.id === data.region_id);
  const t = data.totals;
  const radio = data.channels.find((c) => c.channel === "radio");
  const atc = data.channels.find((c) => c.channel === "atollcare");
  const gain = radio?.median_warning_min != null && atc?.median_warning_min != null ? atc.median_warning_min - radio.median_warning_min : null;
  const daily = data.daily.map((d) => ({
    day: new Date(d.day).toLocaleDateString("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }),
    Radio: d.radio,
    AtollCare: d.atollcare,
    Warning: d.avg_warning_min != null ? Math.round(d.avg_warning_min) : null,
  }));
  const hours = data.by_hour.map((h) => ({ hour: h.key, Transfers: h.transfers }));

  return (
    <div className="flex flex-col gap-[1rem]">
      <div className="grid grid-cols-2 gap-[1rem] lg:grid-cols-4">
        <Tile label="Median warning before arrival" value={fmtMin(t.median_warning_min)} note="Handoff sent → patient at the door" />
        <Tile label="Warning delivered" value={`${Math.round(t.warning_hours).toLocaleString("en-GB")} h`} note={`Across ${t.transfers} transfers`} />
        <Tile label="Median time to accept" value={fmtMin(t.median_accept_min)} note={`90th percentile ${fmtMin(t.p90_accept_min)}`} />
        <Tile label="Team prepared before arrival" value={t.prepared_pct != null ? `${Math.round(t.prepared_pct)}%` : "—"} note={`Median journey ${fmtMin(t.median_journey_min)}`} />
      </div>

      <Card
        title="Transfers per day and average warning"
        aside={<span className="text-[0.8125rem] text-ink-3">Bars: transfers by channel · line: average minutes of warning</span>}
      >
        <div className="h-[18rem]">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={daily} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
              <CartesianGrid stroke="var(--line)" vertical={false} />
              <XAxis dataKey="day" tick={{ fontSize: 12, fill: "var(--ink-3)" }} interval="preserveStartEnd" minTickGap={24} />
              <YAxis yAxisId="n" tick={{ fontSize: 12, fill: "var(--ink-3)" }} allowDecimals={false} />
              <YAxis yAxisId="w" orientation="right" tick={{ fontSize: 12, fill: "var(--ink-3)" }} unit="m" />
              <Tooltip />
              <Bar yAxisId="n" dataKey="Radio" stackId="c" fill={RADIO} />
              <Bar yAxisId="n" dataKey="AtollCare" stackId="c" fill={ATOLLCARE} radius={[3, 3, 0, 0]} />
              <Line yAxisId="w" dataKey="Warning" stroke={WARNING} strokeWidth={2} dot={false} connectNulls />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid grid-cols-1 gap-[1rem] lg:grid-cols-2">
        <Card title="Radio / phone pre-alert vs AtollCare handoff">
          <div className="grid grid-cols-2 gap-[1rem]">
            {[radio, atc].map((c, i) => (
              <div key={i} className="flex flex-col gap-[.5rem]">
                <span className="flex items-center gap-[.5rem] text-[0.875rem] font-[600]">
                  <span className="h-[.625rem] w-[.625rem] rounded-full" style={{ background: i ? ATOLLCARE : RADIO }} />
                  {i ? "AtollCare" : "Radio / phone"}
                </span>
                <span className="text-[1.5rem] font-[650] tabular-nums">{fmtMin(c?.median_warning_min)}</span>
                <span className="text-[0.8125rem] text-ink-2">median warning · {c?.transfers ?? 0} transfers</span>
                <span className="text-[0.8125rem] text-ink-2">
                  accept {fmtMin(c?.median_accept_min)} · prepared {c?.prepared_pct != null ? `${Math.round(c.prepared_pct)}%` : "—"}
                </span>
              </div>
            ))}
          </div>
          {gain != null && gain > 0 && (
            <p className="mt-[1rem] rounded-[.75rem] bg-teal-soft p-[.75rem] text-[0.9375rem] text-teal-strong">
              Receiving teams get a median <strong>{fmtMin(gain)} more warning</strong> per patient with a structured handoff.
            </p>
          )}
        </Card>

        <Card title="Departures by local hour" aside={<span className="text-[0.8125rem] text-ink-3">{region?.timezone}</span>}>
          <div className="h-[13rem]">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={hours} margin={{ top: 4, right: 4, bottom: 0, left: -16 }}>
                <CartesianGrid stroke="var(--line)" vertical={false} />
                <XAxis dataKey="hour" tick={{ fontSize: 12, fill: "var(--ink-3)" }} interval={2} />
                <YAxis tick={{ fontSize: 12, fill: "var(--ink-3)" }} allowDecimals={false} />
                <Tooltip />
                <Bar dataKey="Transfers" fill={WARNING} radius={[3, 3, 0, 0]} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 gap-[1rem] lg:grid-cols-2">
        <Card title="By transport mode">
          <GroupTable rows={data.by_mode} metric="journey" label={(k) => MODE_LABEL[k as keyof typeof MODE_LABEL] ?? k} />
        </Card>
        <Card title="By receiving hospital">
          <GroupTable rows={data.by_destination} metric="accept" label={(k) => place(region, k)} />
        </Card>
      </div>
    </div>
  );
}

export default function () {
  const [days, setDays] = useState<(typeof WINDOWS)[number]>("60");
  const { data, isLoading } = useInsights(Number(days));
  const { data: meta } = useMeta();
  const [seeding, setSeeding] = useState(false);

  const seed = async () => {
    setSeeding(true);
    try {
      const res = await post<SeedResponse>("/insights/seed?days=60");
      toast(`Seeded ${res.inserted} transfers in ${(res.elapsed_ms / 1000).toFixed(1)} s`);
      await mutate((key) => typeof key === "string" && key.startsWith("/insights"));
    } catch (err) {
      toastError(err);
    } finally {
      setSeeding(false);
    }
  };

  return (
    <div className="flex flex-col gap-[1.25rem]">
      <header className="flex flex-wrap items-end justify-between gap-[1rem]">
        <div className="flex flex-col gap-[.375rem]">
          <h1 className="text-[1.5rem] font-[650] tracking-[-0.02em]">Network insights</h1>
          <p className="text-ink-2">
            How long receiving teams know a patient is coming, across every completed transfer
            {meta ? ` in ${meta.region.name}` : ""}.
          </p>
          {data && (
            <div className="flex flex-wrap gap-[.5rem]">
              <PillBase>
                <Database size={13} /> {data.source === "transfer_daily" ? "Tiger Data · continuous aggregate" : data.source === "raw" ? "Postgres · raw query" : "In-memory"} · {data.query_ms} ms
              </PillBase>
              {meta && <PillBase>{meta.infra.database}</PillBase>}
              {data.totals.seeded > 0 && <PillBase className="bg-caution-soft text-caution">Synthetic history · {data.totals.seeded} seeded transfers</PillBase>}
            </div>
          )}
        </div>
        <Segmented label="Window" size="sm" value={days} onChange={(v) => setDays(v)} options={WINDOWS.map((w) => ({ value: w, label: `${w} days` }))} />
      </header>

      {isLoading && !data && <Skeleton className="h-[20rem]" />}
      {data && data.totals.transfers === 0 && <Empty onSeed={seed} busy={seeding} />}
      {data && data.totals.transfers > 0 && <Body data={data} />}
    </div>
  );
}
