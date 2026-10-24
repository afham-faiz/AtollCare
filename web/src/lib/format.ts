// Formatting helpers: minutes, sim-clock local times (Indian/Maldives), labels.
import type { CaseStatus, Facility, Severity, TransportMode } from "@/lib/api";

export const TZ = "Indian/Maldives";

export function fmtMin(min?: number | null): string {
  if (min === null || min === undefined || Number.isNaN(min)) return "—";
  const m = Math.round(min);
  const sign = m < 0 ? "−" : "";
  const a = Math.abs(m);
  if (a < 60) return `${sign}${a} min`;
  return `${sign}${Math.floor(a / 60)} h ${String(a % 60).padStart(2, "0")} min`;
}

export function fmtTime(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: TZ });
}

export function minutesBetween(a?: string | null, b?: string | null): number | null {
  if (!a || !b) return null;
  return (new Date(b).getTime() - new Date(a).getTime()) / 60000;
}

export function fmtRelative(iso: string, nowIso?: string | null): string {
  const m = minutesBetween(iso, nowIso ?? new Date().toISOString());
  if (m === null) return "";
  if (Math.abs(m) < 1) return "now";
  return m > 0 ? `${fmtMin(m)} ago` : `in ${fmtMin(-m)}`;
}

export const MODE_LABEL: Record<TransportMode, string> = {
  ground: "Ground",
  speedboat: "Speedboat",
  sea_ambulance: "Sea ambulance",
  seaplane: "Seaplane",
  fixed_wing: "Fixed-wing",
  helicopter: "Helicopter",
};

export const MODE_COLOR: Record<TransportMode, string> = {
  ground: "#5b6670",
  speedboat: "#0e7c86",
  sea_ambulance: "#0b5f67",
  seaplane: "#f79009",
  fixed_wing: "#6b4fbb",
  helicopter: "#d92d20",
};

export const SEVERITY_LABEL: Record<Severity, string> = {
  low: "Low",
  low_medium: "Low–medium",
  medium: "Medium",
  high: "High",
  critical: "Critical",
};

export const STATUS_LABEL: Record<CaseStatus, string> = {
  draft: "Draft",
  submitted: "Submitted",
  assessed: "Assessed",
  referred: "Referred",
  needs_info: "Needs info",
  accepted: "Accepted",
  declined: "Declined",
  dispatched: "Dispatched",
  in_transit: "In transit",
  arrived: "Arrived",
  closed: "Closed",
};

export const CONDITION_LABEL: Record<string, string> = {
  stemi: "Heart attack (STEMI)",
  stroke: "Stroke",
  major_trauma: "Major trauma",
  pph: "Postpartum haemorrhage",
  sepsis: "Sepsis",
  respiratory_failure: "Breathing difficulty",
  appendicitis: "Appendicitis",
  other: "Undifferentiated",
};

export function facilityName(facilities: Facility[] | undefined, id?: string | null): string {
  if (!id) return "—";
  const f = facilities?.find((x) => x.id === id);
  return f ? f.short_name || f.name : id;
}
