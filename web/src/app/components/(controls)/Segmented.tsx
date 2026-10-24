// Segmented control with a sliding selection indicator.
"use client";

import { useLayoutEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import styles from "./Segmented.module.scss";

export type SegmentOption<T extends string> = { value: T; label: React.ReactNode; title?: string };

export default function <T extends string>({
  options,
  value,
  onChange,
  size = "md",
  className,
  label,
}: {
  options: SegmentOption<T>[];
  value: T | null;
  onChange: (v: T) => void;
  size?: "sm" | "md";
  className?: string;
  label: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    const track = ref.current;
    if (!track) return;
    // measure the selected segment so the indicator can glide to it — again whenever the track resizes
    const measure = () => {
      const el = track.querySelector<HTMLButtonElement>('[aria-checked="true"]');
      setIndicator(el ? { left: el.offsetLeft, width: el.offsetWidth } : null);
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(track);
    return () => ro.disconnect();
  }, [value, options.length]);

  return (
    <div ref={ref} role="radiogroup" aria-label={label} className={twMerge(styles.track, styles[size], className)}>
      {indicator && <span className={styles.indicator} style={{ transform: `translateX(${indicator.left}px)`, width: indicator.width }} aria-hidden />}
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          title={o.title}
          onClick={() => onChange(o.value)}
          className={styles.segment}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
