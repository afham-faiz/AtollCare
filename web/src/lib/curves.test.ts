import { describe, expect, test } from "bun:test";

import { areaPath, project, smoothPath } from "./curves";

describe("project", () => {
  test("spans the width and puts the largest value at the top", () => {
    const pts = project([0, 5, 10], { width: 100, height: 50, pad: 0 });
    expect(pts.map((p) => p[0])).toEqual([0, 50, 100]);
    expect(pts[2][1]).toBe(0);
    expect(pts[0][1]).toBe(50);
  });

  test("a flat signal stays inside the box", () => {
    const pts = project([7, 7, 7], { width: 10, height: 10, pad: 1 });
    for (const [, y] of pts) expect(y).toBeGreaterThanOrEqual(1);
  });
});

describe("smoothPath", () => {
  test("starts at the first point and ends at the last with one curve per gap", () => {
    const d = smoothPath([
      [0, 10],
      [10, 0],
      [20, 10],
    ]);
    expect(d.startsWith("M0,10")).toBe(true);
    expect(d.endsWith("20,10")).toBe(true);
    expect(d.match(/C/g)?.length).toBe(2);
  });

  test("handles empty and single-point input", () => {
    expect(smoothPath([])).toBe("");
    expect(smoothPath([[3, 4]])).toBe("M3,4");
  });

  test("area closes down to the baseline", () => {
    expect(areaPath([[0, 1], [5, 2]], 9).endsWith("L5,9 L0,9 Z")).toBe(true);
  });
});
