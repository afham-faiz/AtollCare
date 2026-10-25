// Formatting helpers. Times are shown in the transfer region's timezone.
import type { Facility, Region, TransportMode } from "@/lib/api";

export function fmtMin(min?: number | null): string {
  if (min === null || min === undefined || Number.isNaN(min)) return "—";
  const m = Math.max(0, Math.round(min));
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

export function fmtTime(iso: string | null | undefined, tz?: string): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZone: tz });
}

export function minutesUntil(iso: string | null | undefined, nowIso: string | null | undefined): number | null {
  if (!iso || !nowIso) return null;
  return (new Date(iso).getTime() - new Date(nowIso).getTime()) / 60000;
}

export function ago(iso: string, nowIso?: string | null): string {
  const m = (new Date(nowIso ?? Date.now()).getTime() - new Date(iso).getTime()) / 60000;
  if (m < 1) return "just now";
  return `${fmtMin(m)} ago`;
}

export const MODE_LABEL: Record<TransportMode, string> = {
  road: "Road ambulance",
  boat: "Sea ambulance",
  helicopter: "Helicopter",
  plane: "Air ambulance",
};

export function facility(region: Region | undefined, id: string | null | undefined): Facility | undefined {
  return region?.facilities.find((f) => f.id === id);
}

export function place(region: Region | undefined, id: string | null | undefined): string {
  return facility(region, id)?.short_name ?? id ?? "—";
}

export function patientLine(p: { age?: number | null; sex?: string | null }): string {
  const sex = p.sex === "M" ? "M" : p.sex === "F" ? "F" : p.sex === "X" ? "X" : "";
  return [p.age ? `${p.age}` : null, sex].filter(Boolean).join(" ") || "Patient";
}

export const NEWS2_LABEL: Record<string, string> = {
  low: "Low",
  low_medium: "Low–medium",
  medium: "Medium",
  high: "High",
};

export function num(v: unknown): number | null {
  return typeof v === "number" ? v : null;
}

/** "Dhangethi Health Centre (Alif Dhaalu)" → the place and its atoll, for a two-line label. */
export function splitPlace(name: string): { name: string; area: string | null } {
  const m = name.match(/^(.*?)\s*\(([^)]+)\)\s*$/);
  return m ? { name: m[1], area: m[2] } : { name, area: null };
}
