// F-M3.9 Time-saved panel: stacked bars (phone-chain baseline vs ours) + assumptions popover (F-M2.9).
"use client";

import { Info } from "lucide-react";
import { useState } from "react";

import Card from "@/app/components/Card";
import SourceBadge from "@/app/components/SourceBadge";
import type { BaselineComparison } from "@/lib/api";
import { fmtMin } from "@/lib/format";

const SHADES = ["#c9ced3", "#aeb5bc", "#949ca5", "#7a848e", "#606b76", "#47525d"];

function Bar({ steps, total, max, tone }: { steps: BaselineComparison["steps"]; total: number; max: number; tone: "base" | "ours" }) {
  return (
    <div className="flex h-[1.75rem] w-full overflow-hidden rounded-[.375rem] bg-surface">
      {steps
        .filter((s) => s.min > 0)
        .map((s, i) => (
          <div
            key={s.id}
            title={`${s.label}: ${fmtMin(s.min)}`}
            style={{
              width: `${(s.min / max) * 100}%`,
              background: tone === "ours" ? (i === 0 ? "var(--brand)" : "color-mix(in srgb, var(--brand) 55%, transparent)") : SHADES[i % SHADES.length],
            }}
            className="h-full border-r-[1px] border-bg"
          />
        ))}
      <span className="sr-only">{fmtMin(total)}</span>
    </div>
  );
}

export default function ({ baseline, className }: { baseline: BaselineComparison; className?: string }) {
  const [open, setOpen] = useState(false);
  const max = Math.max(baseline.baseline_total_min, baseline.ours_total_min, 1);
  const assumptions = (baseline.assumptions?.steps ?? {}) as Record<string, number | string>;
  return (
    <Card
      title="Time saved vs phone chain"
      className={className}
      aside={
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex min-h-[2.75rem] items-center gap-[.25rem] text-[0.875rem] text-brand"
          aria-expanded={open}
        >
          <Info size={16} /> Assumptions
        </button>
      }
    >
      <p className="text-[2rem] font-bold leading-none tabular-nums text-brand">{fmtMin(baseline.saved_vs_baseline_min)}</p>
      <p className="mb-[.75rem] text-[0.875rem] text-muted">estimated saving per case</p>
      <div className="flex flex-col gap-[.5rem]">
        <div>
          <div className="mb-[.25rem] flex justify-between text-[0.875rem]">
            <span>Sequential phone chain</span>
            <span className="tabular-nums">{fmtMin(baseline.baseline_total_min)}</span>
          </div>
          <Bar steps={baseline.steps} total={baseline.baseline_total_min} max={max} tone="base" />
        </div>
        <div>
          <div className="mb-[.25rem] flex justify-between text-[0.875rem]">
            <span>Parallel handoffs (ours)</span>
            <span className="tabular-nums">{fmtMin(baseline.ours_total_min)}</span>
          </div>
          <Bar steps={baseline.ours_steps} total={baseline.ours_total_min} max={max} tone="ours" />
        </div>
      </div>
      {open && (
        <div className="mt-[.75rem] rounded-[.5rem] border-[1px] border-border p-[.75rem] text-[0.875rem]">
          <div className="mb-[.5rem]">
            <SourceBadge kind="assumption" /> <span className="text-muted">engine/app/data/baseline.yaml</span>
          </div>
          <ul className="flex flex-col gap-[.25rem]">
            {baseline.steps.map((s) => (
              <li key={s.id} className="flex justify-between gap-[1rem]">
                <span>{s.label}</span>
                <span className="tabular-nums">{String(assumptions[s.id] ?? s.min)}{typeof assumptions[s.id] === "number" ? " min" : ""}</span>
              </li>
            ))}
            {baseline.ours_steps.map((s) => (
              <li key={s.id} className="flex justify-between gap-[1rem] text-brand">
                <span>{s.label}</span>
                <span className="tabular-nums">{fmtMin(s.min)}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Card>
  );
}
