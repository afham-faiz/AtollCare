// NEWS2-driven urgency: score, band in words, icon. Critical red only for genuine clinical urgency.
import { AlertTriangle, Activity } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { News2Result } from "@/lib/api";
import { NEWS2_WORD, news2Level } from "@/lib/clinical";

export default function ({ news2, size = "md", className }: { news2?: News2Result | null; size?: "md" | "lg"; className?: string }) {
  const level = news2Level(news2?.total, news2?.any_single_3);
  if (!news2 || level === null) {
    return <span className={twMerge("inline-flex items-center gap-[.375rem] text-[0.875rem] text-ink-3", className)}>NEWS2 pending</span>;
  }
  const cls =
    level === "urgent"
      ? "bg-critical text-white"
      : level === "watch"
        ? "bg-caution-soft text-caution"
        : "bg-[var(--sage-100)] text-[var(--sage-700)]";
  const Icon = level === "normal" ? Activity : AlertTriangle;
  return (
    <span
      className={twMerge(
        "inline-flex items-center gap-[.5rem] whitespace-nowrap rounded-full font-[500]",
        size === "lg" ? "py-[.375rem] pl-[.625rem] pr-[.875rem] text-[0.9375rem]" : "py-[.25rem] pl-[.5rem] pr-[.75rem] text-[0.8125rem]",
        cls,
        className,
      )}
    >
      <Icon size={size === "lg" ? 16 : 14} strokeWidth={1.75} />
      <span className="tnum">NEWS2 {news2.total}</span>
      <span className="opacity-80">· {news2.band ? NEWS2_WORD[news2.band] : ""}{news2.complete ? "" : " (partial)"}</span>
    </span>
  );
}
