// Display helpers for clinical values: status words (never colour alone), provenance and freshness, series for trends.
// Thresholds mirror the engine's NEWS2 bands; the engine remains the source of truth for scores and alerts.
import type { LatestValue, Transfer } from "@/lib/api";

export type Level = "normal" | "watch" | "urgent";

export type Assessment = { level: Level; word: string };

const band = (score: number, high: boolean): Assessment =>
  score === 0
    ? { level: "normal", word: "In range" }
    : score === 3
      ? { level: "urgent", word: high ? "Very high" : "Very low" }
      : { level: "watch", word: high ? "Raised" : "Low" };

export function assessHr(v: number): Assessment {
  if (v <= 40) return band(3, false);
  if (v <= 50) return band(1, false);
  if (v <= 90) return band(0, false);
  if (v <= 110) return band(1, true);
  if (v <= 130) return band(2, true);
  return band(3, true);
}

export function assessRr(v: number): Assessment {
  if (v <= 8) return band(3, false);
  if (v <= 11) return band(1, false);
  if (v <= 20) return band(0, false);
  if (v <= 24) return band(2, true);
  return band(3, true);
}

export function assessSpo2(v: number): Assessment {
  if (v <= 91) return { level: "urgent", word: "Very low" };
  if (v <= 95) return { level: "watch", word: "Low" };
  return { level: "normal", word: "In range" };
}

export function assessSbp(v: number): Assessment {
  if (v <= 90) return band(3, false);
  if (v <= 110) return band(1, false);
  if (v <= 219) return band(0, false);
  return band(3, true);
}

export function assessTemp(v: number): Assessment {
  if (v <= 35) return band(3, false);
  if (v <= 36) return band(1, false);
  if (v <= 38) return band(0, false);
  if (v <= 39) return band(1, true);
  return band(2, true);
}

export function news2Level(total: number | null | undefined, anySingle3 = false): Level | null {
  if (total === null || total === undefined) return null;
  if (total >= 7) return "urgent";
  if (total >= 5 || anySingle3) return "watch";
  return "normal";
}

export const NEWS2_WORD: Record<string, string> = {
  low: "Low risk",
  low_medium: "Low–medium risk",
  medium: "Medium risk",
  high: "High risk",
};

// ─── provenance ──────────────────────────────────────────────────────────────
export type Source = "presage" | "manual" | "simulated";

export const SOURCE_LABEL: Record<Source, string> = {
  presage: "Presage",
  manual: "Crew",
  simulated: "Simulated",
};

export function freshness(at: string, now?: string | null): string {
  const s = (new Date(now ?? Date.now()).getTime() - new Date(at).getTime()) / 1000;
  if (s < 45) return "now";
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  return `${Math.floor(m / 60)} h ${m % 60} min ago`;
}

export function provenance(lv: LatestValue | undefined, now?: string | null): string {
  if (!lv) return "Not recorded";
  return `${SOURCE_LABEL[lv.source as Source]} · ${freshness(lv.at, now)}`;
}

export function numeric(lv: LatestValue | undefined): number | null {
  return lv && typeof lv.value === "number" ? lv.value : null;
}

// ─── series for sparklines (real recorded readings only) ─────────────────────
export type Point = { t: number; v: number; source: Source };

export function series(t: Transfer, field: "heart_rate" | "resp_rate" | "spo2", minutes = 30): Point[] {
  const end = t.vitals.length ? new Date(t.vitals[t.vitals.length - 1].recorded_at).getTime() : 0;
  return t.vitals
    .filter((r) => r[field] != null && !r.low_quality && end - new Date(r.recorded_at).getTime() <= minutes * 60000)
    .map((r) => ({ t: new Date(r.recorded_at).getTime(), v: r[field] as number, source: r.source as Source }));
}

export const sexWord = (s?: string | null) => (s === "M" ? "Male" : s === "F" ? "Female" : s === "X" ? "Other" : null);

export function patientTitle(p: { age?: number | null; sex?: string | null }): string {
  return [p.age ? `${p.age}` : null, sexWord(p.sex)].filter(Boolean).join(" · ") || "Patient";
}
