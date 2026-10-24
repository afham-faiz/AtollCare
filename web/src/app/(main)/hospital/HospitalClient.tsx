// F-M3.1 Referral inbox: facility selector, cases sorted by severity then window margin, critical rows pulse.
"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import { DEFAULT_HOSPITAL_ID } from "@/app/config";
import Card from "@/app/components/Card";
import PillSeverity from "@/app/components/(pills)/PillSeverity";
import PillStatus from "@/app/components/(pills)/PillStatus";
import Skeleton from "@/app/components/Skeleton";
import { CONDITION_LABEL, facilityName, fmtMin, fmtTime } from "@/lib/format";
import { useCases, useMeta } from "@/lib/swr";

import CapacityPanel from "./CapacityPanel";
import styles from "./Hospital.module.scss";

const FAC_KEY = "atollcare.hospital";

export default function () {
  const { data: meta } = useMeta();
  const [fid, setFid] = useState(DEFAULT_HOSPITAL_ID);
  const { data: cases } = useCases(`?destination_id=${fid}`);
  const firstSeen = useRef<Map<string, number>>(new Map());
  const [, force] = useState(0);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(FAC_KEY);
      if (saved) setFid(saved);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    if (!cases) return;
    const initial = firstSeen.current.size === 0;
    for (const c of cases) if (!firstSeen.current.has(c.id)) firstSeen.current.set(c.id, initial ? 0 : Date.now());
    const t = setTimeout(() => force((n) => n + 1), 10500);
    return () => clearTimeout(t);
  }, [cases]);

  const hospitals = (meta?.facilities ?? []).filter((f) => f.type.endsWith("hospital"));
  const visible = (cases ?? []).filter((c) => c.status !== "draft");

  return (
    <div className="grid gap-[1rem] lg:grid-cols-[1fr_22rem]">
      <div className="flex min-w-0 flex-col gap-[1rem]">
        <div className="flex flex-wrap items-center gap-[.75rem]">
          <h1 className="text-[1.5rem] font-bold">Referral inbox</h1>
          <select
            value={fid}
            onChange={(e) => {
              setFid(e.target.value);
              try {
                localStorage.setItem(FAC_KEY, e.target.value);
              } catch {
                // ignore
              }
            }}
            className="h-[2.75rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.75rem]"
            aria-label="Facility"
          >
            {hospitals.map((h) => (
              <option key={h.id} value={h.id}>
                {h.name}
              </option>
            ))}
          </select>
        </div>
        <Card>
          {!cases && <Skeleton className="h-[8rem]" />}
          {cases && visible.length === 0 && (
            <p className="text-muted">No incoming cases. Load a scenario in <Link href="/demo" className="text-brand underline">/demo</Link>.</p>
          )}
          {visible.length > 0 && (
            <div className="overflow-x-auto">
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>Case</th>
                    <th>Severity</th>
                    <th>Condition</th>
                    <th>Origin</th>
                    <th>Since onset</th>
                    <th>Window left</th>
                    <th>Status</th>
                    <th>ETA</th>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((c) => {
                    const seen = firstSeen.current.get(c.id) ?? 0;
                    const pulse = c.severity === "critical" && seen > 0 && Date.now() - seen < 10000;
                    const remaining = c.window_remaining_min;
                    return (
                      <tr key={c.id} className={twMerge(pulse && "animate-pulse-alert")}>
                        <td>
                          <Link href={`/hospital/${c.id}`} className="font-bold text-brand tabular-nums">
                            {c.short_code}
                          </Link>
                          {c.status === "assessed" && <span className="block text-[0.875rem] text-muted">pre-alert</span>}
                        </td>
                        <td><PillSeverity severity={c.severity} /></td>
                        <td>{CONDITION_LABEL[c.primary_condition_id ?? "other"] ?? c.primary_condition_id}</td>
                        <td>{facilityName(meta?.facilities, c.origin_facility_id)}</td>
                        <td className="tabular-nums">{fmtMin(c.time_since_onset_min)}</td>
                        <td className={twMerge("tabular-nums font-semibold", remaining !== null && remaining !== undefined && remaining < 30 && "text-alert")}>
                          {remaining === null || remaining === undefined ? "—" : remaining < 0 ? `breached ${fmtMin(-remaining)}` : fmtMin(remaining)}
                        </td>
                        <td><PillStatus status={c.status} /></td>
                        <td className="tabular-nums">{fmtTime(c.eta)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
      {meta && <CapacityPanel facilities={meta.facilities} focusId={fid} />}
    </div>
  );
}
