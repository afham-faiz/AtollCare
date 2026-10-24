// Live chest-movement trace from Presage (breathing.upperTrace), normalised to the box.
export default function ({ trace, className }: { trace: number[]; className?: string }) {
  if (trace.length < 4) return null;
  const min = Math.min(...trace);
  const max = Math.max(...trace);
  const span = max - min || 1;
  const pts = trace.map((v, i) => `${(i / (trace.length - 1)) * 100},${36 - ((v - min) / span) * 32}`).join(" ");
  return (
    <svg viewBox="0 0 100 40" preserveAspectRatio="none" className={className} aria-label="Breathing waveform">
      <polyline points={pts} fill="none" stroke="#0e7c86" strokeWidth="1.6" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}
