// Every Presage measurement on a transfer, wherever it came from: the companion's phone before anyone moved (a
// bystander estimate, never scored), the crew's phone scans, or a mounted camera's continuous stream.
import type { Scan, Transfer } from "@/lib/api";
import type { Point } from "@/lib/clinical";

export type ContactlessReading = {
  at: string;
  hr: number | null;
  rr: number | null;
  stable: boolean; // Presage's own verdict (a bystander reading is never scored, stable or not)
  who: "companion" | "crew" | "monitor";
  scan?: Scan;
  pulse: Point[]; // heart rate across the scan, for a sparkline
};

const ms = (iso: string) => new Date(iso).getTime();

function fromScan(scan: Scan, who: "companion" | "crew"): ContactlessReading | null {
  const v = scan.vitals;
  if (!v || v.source !== "presage" || (v.heart_rate_bpm == null && v.respiration_rate_bpm == null)) return null;
  const series = ((v.diagnostics as { pulse_series?: { t_s: number; value: number; stable?: boolean }[] } | undefined)?.pulse_series ?? []).filter((s) => s.stable);
  return {
    at: scan.at,
    hr: v.heart_rate_bpm ?? null,
    rr: v.respiration_rate_bpm ?? null,
    stable: !!(v.heart_rate_stable || v.respiration_stable),
    who,
    scan,
    pulse: series.map((s) => ({ t: ms(scan.at) + s.t_s * 1000, v: s.value, source: "presage" })),
  };
}

export function contactless(t: Transfer): { all: ContactlessReading[]; latest: ContactlessReading | null; first: string | null } {
  const scans = [
    ...(t.pre_arrival?.scans ?? []).map((s) => fromScan(s, "companion")),
    ...t.scans.map((s) => fromScan(s, "crew")),
  ].filter((r): r is ContactlessReading => !!r);
  // the continuous stream: Presage readings that aren't a scan's own (scan readings carry the scan's time)
  const scanTimes = new Set(t.scans.map((s) => ms(s.at)));
  const stream = t.vitals
    .filter((r) => r.source === "presage" && !scanTimes.has(ms(r.recorded_at)) && (r.heart_rate != null || r.resp_rate != null))
    .map((r): ContactlessReading => ({
      at: r.recorded_at,
      hr: r.heart_rate ?? null,
      rr: r.resp_rate ?? null,
      stable: !r.low_quality,
      who: "monitor",
      pulse: [],
    }));
  const all = [...scans, ...stream].sort((a, b) => ms(a.at) - ms(b.at));
  return { all, latest: all.at(-1) ?? null, first: all[0]?.at ?? null };
}

/** Minutes between the first contactless reading and arrival (or the ETA while still on the way). */
export function knownBeforeArrival(t: Transfer, first: string | null): number | null {
  if (!first) return null;
  const minutes = (ms(t.arrived_at ?? t.eta) - ms(first)) / 60000;
  return minutes >= 1 ? Math.round(minutes) : null;
}
