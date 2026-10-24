// Small status dot. "live" breathes gently; others are still.
import { twMerge } from "tailwind-merge";

const TONE = {
  live: "bg-teal [animation:live-pulse_2s_var(--ease-out)_infinite]",
  teal: "bg-teal",
  accent: "bg-accent",
  caution: "bg-caution-fill",
  critical: "bg-critical",
  idle: "bg-ink-3",
} as const;

export default function ({ tone, className }: { tone: keyof typeof TONE; className?: string }) {
  return <span aria-hidden className={twMerge("inline-block h-[.5rem] w-[.5rem] shrink-0 rounded-full", TONE[tone], className)} />;
}
