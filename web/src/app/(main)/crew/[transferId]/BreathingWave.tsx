// Live chest-movement trace from Presage (breathing.upperTrace), normalised to the box. Only shown when live.
export default function ({ trace, className }: { trace: number[]; className?: string }) {
  if (trace.length < 4) return null;
  const min = Math.min(...trace);
  const max = Math.max(...trace);
  const span = max - min || 1;
  const pts = trace.map((v, i) => `${(i / (trace.length - 1)) * 120},${33 - ((v - min) / span) * 30}`).join(" ");
  return (
    <svg viewBox="0 0 120 36" preserveAspectRatio="none" className={className} aria-label="Live breathing waveform">
      <polyline points={pts} fill="none" stroke="#0f9286" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
