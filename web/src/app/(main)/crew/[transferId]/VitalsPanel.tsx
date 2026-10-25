// Vital signs, typeset: value, unit, status in words, provenance and freshness, a trend of real recorded readings.
"use client";

import { AlertTriangle, Plus } from "lucide-react";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

import LiveDot from "@/app/components/(controls)/LiveDot";
import UrgencyBadge from "@/app/components/(transfer)/UrgencyBadge";
import { Bars, Heartbeat, Trace } from "@/app/components/(vitals)/Signal";
import type { Transfer } from "@/lib/api";
import {
  assessHr,
  assessRr,
  assessSbp,
  assessSpo2,
  assessTemp,
  freshness,
  numeric,
  series,
  type Assessment,
} from "@/lib/clinical";

import styles from "./VitalsPanel.module.scss";

export type LiveReading = { value: number | null; stable: boolean } | null;

// Presage's FDA clearance (K254169): pulse 50–150 bpm, breathing 8–26 /min. Outside it the number stays, flagged.
const PRESAGE_HR = [50, 150] as const;
const PRESAGE_RR = [8, 26] as const;
const outside = (v: number | null, [lo, hi]: readonly [number, number]) => v !== null && (v < lo || v > hi);

function Status({ a }: { a: Assessment | null }) {
  if (!a) return null;
  return <span className={twMerge(styles.status, styles[a.level])}>{a.word}</span>;
}

function Source({ kind, at, now }: { kind: "live" | "acquiring" | "presage" | "manual" | "simulated" | "none"; at?: string; now?: string }) {
  if (kind === "live") return <span className={styles.source}><LiveDot tone="live" /> Presage · live</span>;
  if (kind === "acquiring") return <span className={styles.source}><LiveDot tone="accent" /> Presage · acquiring</span>;
  if (kind === "simulated") return <span className={styles.source}>Simulated, not measured</span>;
  if (kind === "none") return <span className={styles.source}>Not recorded</span>;
  return <span className={styles.source}>{kind === "presage" ? "Presage" : "Crew"} · {at ? freshness(at, now) : ""}</span>;
}

function Metric({
  label,
  value,
  unit,
  assessment,
  source,
  flag,
  mark,
  aside,
  simulated,
}: {
  label: string;
  value: number | null;
  unit: string;
  assessment: Assessment | null;
  source: React.ReactNode;
  flag?: string | null;
  mark?: React.ReactNode;
  aside?: React.ReactNode;
  simulated?: boolean;
}) {
  return (
    <div className={styles.metric}>
      <div className={styles.metricHead}>
        <span className={styles.label}>{label}</span>
        {source}
      </div>
      <div className={styles.metricBody}>
        {mark}
        <p className={styles.valueRow}>
          {value === null ? (
            <span className={styles.notYet}>Not measured yet</span>
          ) : (
            <span className={twMerge("numeral value-in", styles.value, simulated && styles.simulated)} key={Math.round(value)}>
              {Math.round(value)}
            </span>
          )}
          {value !== null && <span className="unit">{unit}</span>}
        </p>
        {/* no clinical status for a simulated number: "In range" would assert something that wasn't measured */}
        {value !== null && !simulated && <Status a={assessment} />}
      </div>
      {aside && <div className={styles.aside}>{aside}</div>}
      {flag && <p className={styles.flag}>{flag}</p>}
    </div>
  );
}

export default function ({
  t,
  now,
  live,
  acquiring,
  hr,
  rr,
  trace,
  onAddVitals,
}: {
  t: Transfer;
  now?: string;
  live: boolean;
  acquiring: boolean;
  hr: LiveReading;
  rr: LiveReading;
  trace: number[];
  onAddVitals: () => void;
}) {
  // a simulated number is only shown while the simulator is what's running: once scans (or a pause) take over, an
  // old simulated value would read as the patient's current state
  const L = t.monitoring.source === "simulated" ? t.latest : Object.fromEntries(Object.entries(t.latest).filter(([, v]) => v?.source !== "simulated"));
  const hrValue = live ? (hr?.stable ? hr.value : null) : numeric(L.heart_rate);
  const rrValue = live ? (rr?.stable ? rr.value : null) : numeric(L.resp_rate);
  const contact = (field: "heart_rate" | "resp_rate", reading: LiveReading) =>
    live ? (reading?.stable ? "live" : "acquiring") : L[field] ? (L[field].source as "presage" | "manual" | "simulated") : "none";
  const hrSeries = series(t, "heart_rate");
  const rrSeries = series(t, "resp_rate");
  const crew = [
    { k: "spo2", label: "SpO₂", unit: "%", a: assessSpo2 },
    { k: "systolic_bp", label: "BP", unit: "sys", a: assessSbp },
    { k: "temperature_c", label: "Temp", unit: "°C", a: assessTemp },
  ] as const;
  const acvpu = L.consciousness?.value;
  const missing = t.news2 && !t.news2.complete;
  const urgent = t.alerts.filter((a) => a.level === "critical");
  const alerts = [...urgent, ...t.alerts.filter((a) => a.level !== "critical")];
  const [allAlerts, setAllAlerts] = useState(false);
  const shown = allAlerts ? alerts : alerts.slice(0, 1);
  const crewAt = crew
    .map((c) => L[c.k]?.at)
    .concat(L.consciousness?.at)
    .filter((at): at is string => !!at)
    .sort()
    .at(-1);

  const bars = (pts: ReturnType<typeof series>) => pts.map((p) => ({ v: p.v, simulated: p.source === "simulated" }));

  return (
    <section className={twMerge("card", styles.panel)} aria-label="Vital signs">
      <header className={styles.header}>
        <h2 className={styles.title}>Vital signs</h2>
        <UrgencyBadge news2={t.news2} />
      </header>

      {alerts.length > 0 && (
        <div className={twMerge(styles.alert, urgent.length ? styles.alertUrgent : styles.alertWatch)} role="alert">
          <AlertTriangle size={16} strokeWidth={1.75} className="mt-[.125rem] shrink-0" />
          <ul className={styles.alertList}>
            {shown.map((a) => (
              <li key={a.code}>{a.text}</li>
            ))}
          </ul>
          {alerts.length > 1 && (
            <button type="button" className={styles.more} onClick={() => setAllAlerts((v) => !v)} aria-expanded={allAlerts}>
              {allAlerts ? "Less" : `+${alerts.length - 1} more`}
            </button>
          )}
        </div>
      )}

      {!live && hrValue === null && rrValue === null ? (
        // nothing measured yet: one quiet line, not two empty tiles
        <p className={styles.nothingYet}>Heart rate and breathing appear here once the camera measures.</p>
      ) : (
      <div className={styles.metrics}>
        <Metric
          label="Heart rate"
          value={hrValue}
          unit="bpm"
          assessment={hrValue !== null ? assessHr(hrValue) : null}
          source={<Source kind={contact("heart_rate", hr)} at={L.heart_rate?.at} now={now} />}
          simulated={contact("heart_rate", hr) === "simulated"}
          mark={live ? <Heartbeat bpm={hr?.stable ? hr.value : null} waiting={!hr?.stable} tone="card" size="sm" /> : undefined}
          flag={(live && outside(hrValue, PRESAGE_HR)) || L.heart_rate?.flag ? "Outside Presage’s cleared range (50–150): confirm with a monitor" : null}
          aside={<Bars values={bars(hrSeries)} tone="hr" label="Recent heart rate readings" />}
        />
        <Metric
          label="Breathing"
          value={rrValue}
          unit="/min"
          assessment={rrValue !== null ? assessRr(rrValue) : null}
          source={<Source kind={contact("resp_rate", rr)} at={L.resp_rate?.at} now={now} />}
          simulated={contact("resp_rate", rr) === "simulated"}
          flag={(live && outside(rrValue, PRESAGE_RR)) || L.resp_rate?.flag ? "Outside Presage’s cleared range (8–26): count it by hand" : null}
          aside={
            live && trace.length > 4 ? (
              <Trace values={trace} tone="rr" dot label="Live breathing wave" className={styles.wave} />
            ) : (
              <Bars values={bars(rrSeries)} tone="rr" label="Recent breathing readings" />
            )
          }
        />
      </div>
      )}
      {live && acquiring && <p className={styles.settle}>Readings appear once Presage calls them steady.</p>}

      <div className={styles.crewGrid}>
        {crew.map((c) => {
          const v = numeric(L[c.k]);
          const a = v !== null ? c.a(v) : null;
          return v === null ? (
            <button key={c.k} type="button" className={twMerge(styles.crewItem, styles.crewAdd)} onClick={onAddVitals}>
              <span className={styles.crewLabel}>{c.label}</span>
              <span className={styles.crewAddText}>
                <Plus size={15} strokeWidth={1.75} /> Add
              </span>
            </button>
          ) : (
            <button key={c.k} type="button" className={styles.crewItem} onClick={onAddVitals} title={`Update ${c.label}`}>
              <span className={styles.crewLabel}>{c.label}</span>
              <span className={twMerge("numeral", styles.crewValue, a && a.level !== "normal" && styles[a.level])}>
                {v}
                <span className="unit">{c.unit}</span>
              </span>
            </button>
          );
        })}
        {acvpu ? (
          <button type="button" className={styles.crewItem} onClick={onAddVitals} title="Update ACVPU">
            <span className={styles.crewLabel}>ACVPU</span>
            <span className={twMerge("numeral", styles.crewValue, acvpu !== "A" && styles.urgent)}>{String(acvpu)}</span>
          </button>
        ) : (
          <button type="button" className={twMerge(styles.crewItem, styles.crewAdd)} onClick={onAddVitals}>
            <span className={styles.crewLabel}>ACVPU</span>
            <span className={styles.crewAddText}>
              <Plus size={15} strokeWidth={1.75} /> Add
            </span>
          </button>
        )}
      </div>
      {(crewAt || missing) && (
        <p className={styles.footnote}>{crewAt ? `Crew-entered ${freshness(crewAt, now)} · tap a reading to update` : "NEWS2 needs SpO₂, BP, temperature and ACVPU"}</p>
      )}
    </section>
  );
}
