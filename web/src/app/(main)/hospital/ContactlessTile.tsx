// The hospital's view of Presage: the latest contactless heart and breathing rate, where and when it was measured,
// how it moved across the scan, and the headline the receiving team cares about: how long before arrival they knew.
"use client";

import { twMerge } from "tailwind-merge";

import Sparkline from "@/app/components/(transfer)/Sparkline";
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

  return (
    <section className={twMerge(styles.contactless, "rise-in")} aria-label="Contactless vitals from Presage">
      <header className={styles.ctHead}>
        <span className={styles.ctEyebrow}>Presage · contactless vitals</span>
        {known !== null && <span className={styles.ctKnown}>Known {fmtMin(known)} before arrival</span>}
      </header>

      {latest ? (
        <>
          <div className={styles.ctBody}>
            <div className={styles.ctNumbers}>
              <span className={styles.ctNumber}>
                <span className={twMerge("tnum", styles.ctValue, !latest.stable && styles.ctUnsteady)}>{latest.hr ?? "—"}</span>
                <span className={styles.ctUnit}>bpm</span>
              </span>
              <span className={styles.ctNumber}>
                <span className={twMerge("tnum", styles.ctValue, !latest.stable && styles.ctUnsteady)}>{latest.rr ?? "—"}</span>
                <span className={styles.ctUnit}>/min</span>
              </span>
            </div>
            {latest.pulse.length > 2 && (
              <div className={styles.ctTrace}>
                <Sparkline points={latest.pulse} color="#c8322a" height={44} className={styles.ctSpark} />
                <span className={styles.ctTraceLabel}>Heart rate across the scan</span>
              </div>
            )}
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
          {all.length > 1 && (
            <ol className={styles.ctHistory} aria-label="Every contactless reading">
              {all.slice(-6).map((r) => (
                <li key={`${r.who}-${r.at}`} className={twMerge(r.who === "companion" && styles.ctBystander)} title={WHO[r.who]}>
                  <span className="tnum">{fmtTime(r.at, tz)}</span>
                  <strong className="tnum">{r.hr ?? "—"}</strong>
                  <span className="tnum">{r.rr ?? "—"}</span>
                </li>
              ))}
            </ol>
          )}
        </>
      ) : (
        <p className={styles.ctMeta}>Presage is measuring a scan…</p>
      )}
    </section>
  );
}
