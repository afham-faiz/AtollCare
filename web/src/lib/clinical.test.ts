// Display helpers must agree with the engine's NEWS2 bands and never claim more than the data says.
import { describe, expect, test } from "bun:test";

import { assessHr, assessRr, assessSbp, assessSpo2, freshness, news2Level, patientTitle, provenance } from "./clinical";

describe("status words follow NEWS2 bands", () => {
  test("heart rate", () => {
    expect(assessHr(40)).toEqual({ level: "urgent", word: "Very low" });
    expect(assessHr(72).level).toBe("normal");
    expect(assessHr(105)).toEqual({ level: "watch", word: "Raised" });
    expect(assessHr(131)).toEqual({ level: "urgent", word: "Very high" });
  });

  test("respiration, SpO₂, systolic BP", () => {
    expect(assessRr(16).level).toBe("normal");
    expect(assessRr(25).level).toBe("urgent");
    expect(assessSpo2(95)).toEqual({ level: "watch", word: "Low" });
    expect(assessSpo2(91).level).toBe("urgent");
    expect(assessSbp(104).word).toBe("Low");
    expect(assessSbp(182).level).toBe("normal");
  });

  test("overall level: any single 3 is at least a watch", () => {
    expect(news2Level(null)).toBeNull();
    expect(news2Level(2)).toBe("normal");
    expect(news2Level(2, true)).toBe("watch");
    expect(news2Level(7)).toBe("urgent");
  });
});

describe("provenance", () => {
  const now = "2026-10-24T12:00:00Z";
  test("freshness reads like a clinician would say it", () => {
    expect(freshness("2026-10-24T11:59:30Z", now)).toBe("now");
    expect(freshness("2026-10-24T11:53:00Z", now)).toBe("7 min ago");
    expect(freshness("2026-10-24T10:35:00Z", now)).toBe("1 h 25 min ago");
  });

  test("every value names its source; simulated says so", () => {
    expect(provenance(undefined, now)).toBe("Not recorded");
    expect(provenance({ value: 95, source: "manual", at: "2026-10-24T11:58:00Z", flag: null }, now)).toBe("Crew · 2 min ago");
    expect(provenance({ value: 88, source: "simulated", at: now, flag: null }, now)).toBe("Simulated · now");
  });

  test("patient title", () => {
    expect(patientTitle({ age: 58, sex: "M" })).toBe("58 · Male");
    expect(patientTitle({})).toBe("Patient");
  });
});
