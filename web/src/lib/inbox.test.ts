import { describe, expect, test } from "bun:test";

import { activeFilters, inbox, NO_FILTERS, severityOf } from "./inbox";

const NOW = "2026-10-25T10:00:00Z";
const at = (min: number) => new Date(new Date(NOW).getTime() + min * 60000).toISOString();
type Status = "pending" | "accepted" | "arrived";
const t = (id: string, status: Status, etaMin: number, news2: number | null = null, alert: "warning" | "critical" | null = null) => ({
  id,
  status,
  eta: at(etaMin),
  news2_total: news2,
  alert_level: alert,
});

const items = [
  t("a", "pending", 50, 2),
  t("b", "accepted", 20, 8),
  t("c", "pending", 90, 5),
  t("d", "arrived", -30, 1),
  t("e", "pending", 10, null),
];
const ids = (xs: { id: string }[]) => xs.map((x) => x.id);

describe("severityOf", () => {
  test("NEWS2 bands, with alerts able to raise a transfer", () => {
    expect(severityOf({ news2_total: 8, alert_level: null })).toBe("high");
    expect(severityOf({ news2_total: 5, alert_level: null })).toBe("medium");
    expect(severityOf({ news2_total: 2, alert_level: null })).toBe("low");
    expect(severityOf({ news2_total: 2, alert_level: "critical" })).toBe("high");
    expect(severityOf({ news2_total: null, alert_level: null })).toBeNull();
  });
});

describe("inbox", () => {
  test("no filters: incoming by arrival time, arrived apart", () => {
    const r = inbox(items, NO_FILTERS, NOW);
    expect(ids(r.incoming)).toEqual(["e", "b", "a", "c"]);
    expect(ids(r.arrived)).toEqual(["d"]);
  });

  test("needs response: pending only, no arrived group", () => {
    const r = inbox(items, { ...NO_FILTERS, needsResponse: true }, NOW);
    expect(ids(r.incoming)).toEqual(["e", "a", "c"]);
    expect(r.arrived).toEqual([]);
  });

  test("severity filter and sort", () => {
    expect(ids(inbox(items, { ...NO_FILTERS, severity: "medium" }, NOW).incoming)).toEqual(["c"]);
    expect(ids(inbox(items, { ...NO_FILTERS, sort: "severity" }, NOW).incoming)).toEqual(["b", "c", "e", "a"]);
  });

  test("arriving within a window hides the arrived", () => {
    const r = inbox(items, { ...NO_FILTERS, within: "60" }, NOW);
    expect(ids(r.incoming)).toEqual(["e", "b", "a"]);
    expect(r.arrived).toEqual([]);
  });

  test("counts only the filters that narrow the list", () => {
    expect(activeFilters(NO_FILTERS)).toBe(0);
    expect(activeFilters({ ...NO_FILTERS, sort: "severity" })).toBe(0);
    expect(activeFilters({ needsResponse: true, severity: "high", within: "30", sort: "eta" })).toBe(3);
  });
});
