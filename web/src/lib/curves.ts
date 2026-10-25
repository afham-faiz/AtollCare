// Smooth curves for measured signals (pulse wave, breathing wave, trends): a Catmull-Rom spline through the samples,
// drawn as cubic Béziers, so a trace reads as a signal rather than a jagged polyline. Pure, so it's easy to test.

export type Box = { width: number; height: number; pad?: number };

/** Scale samples into the box (y grows downward; the largest value sits at the top). */
export function project(values: number[], { width, height, pad = 2 }: Box): [number, number][] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const span = Math.max(...values) - min || 1;
  const step = values.length > 1 ? width / (values.length - 1) : 0;
  return values.map((v, i) => [i * step, pad + (1 - (v - min) / span) * (height - pad * 2)]);
}

/** An SVG path through the points; `tension` 0 is straight segments, 1 the full Catmull-Rom curve. */
export function smoothPath(points: [number, number][], tension = 1): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M${fmt(points[0][0])},${fmt(points[0][1])}`;
  const t = tension / 6;
  let d = `M${fmt(points[0][0])},${fmt(points[0][1])}`;
  for (let i = 0; i < points.length - 1; i += 1) {
    const p0 = points[i - 1] ?? points[i];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[i + 2] ?? p2;
    const c1x = p1[0] + (p2[0] - p0[0]) * t;
    const c1y = p1[1] + (p2[1] - p0[1]) * t;
    const c2x = p2[0] - (p3[0] - p1[0]) * t;
    const c2y = p2[1] - (p3[1] - p1[1]) * t;
    d += ` C${fmt(c1x)},${fmt(c1y)} ${fmt(c2x)},${fmt(c2y)} ${fmt(p2[0])},${fmt(p2[1])}`;
  }
  return d;
}

/** The same curve closed down to the baseline, for a soft fill under the line. */
export function areaPath(points: [number, number][], height: number, tension = 1): string {
  if (points.length < 2) return "";
  const last = points[points.length - 1];
  return `${smoothPath(points, tension)} L${fmt(last[0])},${fmt(height)} L${fmt(points[0][0])},${fmt(height)} Z`;
}

const fmt = (n: number) => (Math.round(n * 100) / 100).toString();
