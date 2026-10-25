// The design tokens as plain hex, for the few places that can't read CSS variables (Recharts props, Leaflet path
// options, inline SVG in map markers). Keep in step with web/src/styles/globals.css.
export const PALETTE = {
  ink: "#12201b",
  ink2: "#3e4f48",
  ink3: "#5f6f68",
  ink4: "#8d9b95",
  line: "rgba(18, 32, 27, 0.08)",
  white: "#ffffff",
  sage100: "#dce7df",
  sage300: "#a9c0af",
  sage500: "#6e907a",
  sage700: "#3f6450",
  pine: "#1e3a2f",
  teal: "#2a8a84",
  tealGlow: "#7fd6c8",
  blue500: "#36668f",
  caution: "#9a5b0c",
  critical: "#c0262d",
  seriesHr: "#4e7d5b",
  seriesRr: "#2e8e9a",
  seriesSpo2: "#36668f",
} as const;

/** Recharts chart chrome: no axis lines, at most a few dotted grid lines, small muted ticks, a frosted tooltip. */
export const CHART = {
  grid: { stroke: "rgba(18, 32, 27, 0.08)", strokeDasharray: "2 4", vertical: false },
  tick: { fontSize: 11, fill: PALETTE.ink3 },
  tooltip: {
    borderRadius: 999,
    border: "1px solid rgba(255, 255, 255, 0.6)",
    background: "rgba(246, 249, 247, 0.9)",
    backdropFilter: "blur(16px)",
    boxShadow: "0 18px 40px -18px rgba(18, 32, 27, 0.28)",
    fontSize: 12,
    padding: "6px 14px",
  },
  cursor: { stroke: PALETTE.ink4, strokeWidth: 1 },
} as const;
