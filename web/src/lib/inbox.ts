// The hospital's inbox: which transfers to show and in what order. Pure, so the rules are tested, not eyeballed.
import type { TransferListItem } from "@/lib/api";
import { news2Level } from "@/lib/clinical";

export type Severity = "any" | "high" | "medium" | "low";
export type Within = "any" | "30" | "60" | "120";
export type Sort = "eta" | "severity";
export type InboxFilters = { needsResponse: boolean; severity: Severity; within: Within; sort: Sort };

export const NO_FILTERS: InboxFilters = { needsResponse: false, severity: "any", within: "any", sort: "eta" };

type Item = Pick<TransferListItem, "status" | "eta" | "news2_total" | "alert_level">;

/** high: NEWS2 ≥ 7 or a critical alert; medium: NEWS2 5–6 or a warning; low: scored and below that; null: not scored. */
export function severityOf(t: Pick<Item, "news2_total" | "alert_level">): Exclude<Severity, "any"> | null {
  const level = news2Level(t.news2_total);
  if (level === "urgent" || t.alert_level === "critical") return "high";
  if (level === "watch" || t.alert_level === "warning") return "medium";
  return level === "normal" ? "low" : null;
}

const RANK = { high: 3, medium: 2, low: 1 } as const;

/** How many of the filters are narrowing the list (sorting doesn't count). */
export function activeFilters(f: InboxFilters): number {
  return Number(f.needsResponse) + Number(f.severity !== "any") + Number(f.within !== "any");
}

/** Incoming (on the way) and arrived, filtered and sorted. A time window only makes sense for what's still coming,
 *  so it hides the arrived group, as does showing only what needs a response. */
export function inbox<T extends Item>(items: T[], f: InboxFilters, now: string | undefined): { incoming: T[]; arrived: T[] } {
  const nowMs = now ? new Date(now).getTime() : Date.now();
  const minutes = (t: T) => (new Date(t.eta).getTime() - nowMs) / 60000;
  const keep = (t: T) => {
    if (f.needsResponse && t.status !== "pending") return false;
    if (f.severity !== "any" && severityOf(t) !== f.severity) return false;
    if (f.within !== "any" && (t.status === "arrived" || minutes(t) > Number(f.within))) return false;
    return true;
  };
  const byEta = (a: T, b: T) => new Date(a.eta).getTime() - new Date(b.eta).getTime();
  const bySeverity = (a: T, b: T) => (RANK[severityOf(b) ?? "low"] ?? 0) - (RANK[severityOf(a) ?? "low"] ?? 0) || byEta(a, b);
  const order = f.sort === "severity" ? bySeverity : byEta;
  const shown = items.filter(keep);
  return {
    incoming: shown.filter((t) => t.status !== "arrived").sort(order),
    // newest arrival first
    arrived: shown.filter((t) => t.status === "arrived").sort((a, b) => (f.sort === "severity" ? bySeverity(a, b) : byEta(b, a))),
  };
}
