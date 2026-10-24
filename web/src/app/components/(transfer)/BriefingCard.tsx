// Live SBAR briefing for the receiving team (Gemini, template fallback).
import Card from "@/app/components/Card";
import type { Briefing } from "@/lib/api";
import { ago } from "@/lib/format";

import AiBadge from "./AiBadge";

export default function ({ briefing, now, className }: { briefing?: Briefing | null; now?: string; className?: string }) {
  if (!briefing) return null;
  const rows: [string, string][] = [
    ["Situation", briefing.situation],
    ["Background", briefing.background],
    ["Assessment", briefing.assessment],
    ["Recommendation", briefing.recommendation],
  ];
  return (
    <Card
      className={className}
      title="Briefing"
      aside={
        <span className="flex items-center gap-[.5rem] text-[0.875rem] text-faint">
          updated {ago(briefing.generated_at, now)}
          <AiBadge ai={briefing.generated_by === "gemini"} />
        </span>
      }
    >
      {briefing.suspected_condition && (
        <p className="mb-[.75rem] text-[1.125rem] font-semibold">{briefing.suspected_condition}</p>
      )}
      <dl className="flex flex-col gap-[.75rem]">
        {rows.map(([k, v]) => (
          <div key={k}>
            <dt className="text-[0.875rem] font-semibold text-brand-strong">{k}</dt>
            <dd className="text-[0.9375rem] leading-relaxed">{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
