// The hospital's view of Presage: the latest contactless heart and breathing rate, where and when it was measured,
// how it moved across the scan, and the headline the receiving team cares about: how long before arrival they knew.
"use client";

import { ArrowUpRight } from "lucide-react";
import { twMerge } from "tailwind-merge";

import { Heartbeat, Trace } from "@/app/components/(vitals)/Signal";
import type { Transfer } from "@/lib/api";
import { freshness } from "@/lib/clinical";
import { contactless, knownBeforeArrival, type ContactlessReading } from "@/lib/contactless";
import { fmtMin, fmtTime } from "@/lib/format";

import styles from "./Hospital.module.scss";

const WHO: Record<ContactlessReading["who"], string> = {
  companion: "Companion’s phone",
  crew: "Crew scan",
  monitor: "Crew camera, continuous",
};

export default function ({ t, tz, now }: { t: Transfer; tz?: string; now: string }) {
  const { all, latest, first } = contactless(t);
  const scanning = [...(t.pre_arrival?.scans ?? []), ...t.scans].some((s) => s.status === "processing");
  if (!latest && !scanning) return null;
  const known = knownBeforeArrival(t, first);
  const bystander = latest?.who === "companion";
  const trend = t.alerts.find((a) => a.code === "presage_trend");
  const check = t.presage_checks.at(-1);
  const series = all.filter((r) => r.hr != null);

  return (
    <section className={twMerge("card", styles.contactless, "rise-in")} aria-label="Contactless vitals from Presage">
      <header className={styles.ctHead}>
        <span className={styles.ctEyebrow}>Measured by Presage · contactless</span>
        {known !== null && (
          <span className={styles.ctKnown}>
            <ArrowUpRight size={15} strokeWidth={1.75} /> Known {fmtMin(known)} before arrival
          </span>
        )}
      </header>

      {latest ? (
        <>
          <div className={styles.ctBody}>
            <div className={styles.ctNumbers}>
            <Heartbeat bpm={latest.stable ? latest.hr : null} tone="card" size="md" />
            <div className={styles.ctNumber}>
              <span className={styles.ctLabel}>Heart rate</span>
              <p>
                <span className={twMerge("numeral", styles.ctValue, !latest.stable && styles.ctUnsteady)}>{latest.hr ?? "—"}</span>
                <span className="unit">bpm</span>
              </p>
            </div>
            <div className={styles.ctNumber}>
              <span className={styles.ctLabel}>Breathing</span>
              <p>
                <span className={twMerge("numeral", styles.ctValue, !latest.stable && styles.ctUnsteady)}>{latest.rr ?? "—"}</span>
                <span className="unit">/min</span>
              </p>
            </div>
            </div>
            {/* the scan's own pulse when there is one; otherwise every reading so far, over time */}
            {latest.pulse.length > 2 ? (
              <div className={styles.ctTrace}>
                <Trace values={latest.pulse.map((p) => p.v)} tone="hr" dot label="Heart rate across the scan" />
                <span className={styles.ctTraceLabel}>Heart rate across the scan</span>
              </div>
            ) : series.length > 1 ? (
              <div className={styles.ctTrace}>
                <Trace values={series.map((r) => r.hr as number)} tone="hr" dot label="Heart rate across every reading" />
                <span className={styles.ctTicks}>
                  <span className="tnum">{fmtTime(series[0].at, tz)}</span>
                  <span>Heart rate across {series.length} readings</span>
                  <span className="tnum">{fmtTime(series[series.length - 1].at, tz)}</span>
                </span>
              </div>
            ) : null}
          </div>
          {trend && <p className={styles.ctTrend}>{trend.text}</p>}
          {check && (
            <p className={check.agrees ? styles.ctAgrees : styles.ctTrend}>
              Checked against the crew&apos;s oximeter: camera {check.camera}, oximeter {check.reference} ·{" "}
              {check.agrees ? "agree" : `${Math.abs(check.camera - check.reference)} bpm apart${check.disputed ? ", oximeter used" : ""}`}
            </p>
          )}
          <p className={styles.ctMeta}>
            {WHO[latest.who]} · {fmtTime(latest.at, tz)} · {freshness(latest.at, now)} ·{" "}
            {bystander ? "bystander estimate, not scored" : latest.stable ? "Presage: stable, scored" : "not stable, not scored"}
          </p>
        </>
      ) : (
        <p className={styles.ctMeta}>Presage is measuring a scan…</p>
      )}
    </section>
  );
}
