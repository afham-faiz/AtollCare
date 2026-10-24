// The handoff as a document: SBAR, typeset for reading under pressure. AI-drafted content is labelled as such.
import { Sparkles } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { Briefing, Intervention } from "@/lib/api";
import { freshness } from "@/lib/clinical";
import { fmtTime } from "@/lib/format";

export default function ({
  briefing,
  interventions = [],
  now,
  tz,
  compact = false,
  className,
}: {
  briefing?: Briefing | null;
  interventions?: Intervention[];
  now?: string;
  tz?: string;
  compact?: boolean;
  className?: string;
}) {
  if (!briefing) return null;
  const rows: [string, string][] = [
    ["Situation", briefing.situation],
    ["Background", briefing.background],
    ["Assessment", briefing.assessment],
    ["Recommendation", briefing.recommendation],
  ];
  return (
    <article className={twMerge("flex flex-col", className)}>
      <dl className={twMerge("flex flex-col", compact ? "gap-[.875rem]" : "gap-[1.25rem]")}>
        {rows.map(([k, v]) => (
          <div key={k} className="grid gap-[.25rem] md:grid-cols-[8.5rem_1fr] md:gap-[1.25rem]">
            <dt className="pt-[.125rem] text-[0.8125rem] font-[600] uppercase tracking-[0.06em] text-ink-3">{k}</dt>
            <dd className={twMerge("leading-[1.6] text-ink", compact ? "text-[0.9375rem]" : "text-[1rem]")}>{v}</dd>
          </div>
        ))}
        {interventions.length > 0 && (
          <div className="grid gap-[.25rem] md:grid-cols-[8.5rem_1fr] md:gap-[1.25rem]">
            <dt className="pt-[.125rem] text-[0.8125rem] font-[600] uppercase tracking-[0.06em] text-ink-3">Given</dt>
            <dd>
              <ul className="flex flex-col gap-[.375rem]">
                {interventions.map((i) => (
                  <li key={`${i.note_id}-${i.text}`} className="flex items-baseline gap-[.75rem]">
                    <span className="tnum w-[3rem] shrink-0 text-[0.875rem] text-ink-3">{fmtTime(i.at, tz)}</span>
                    <span className="font-[550]">{i.text}</span>
                  </li>
                ))}
              </ul>
            </dd>
          </div>
        )}
      </dl>
      <p className="mt-[1.25rem] flex items-center gap-[.5rem] text-[0.8125rem] text-ink-3">
        {briefing.generated_by === "gemini" ? <Sparkles size={14} className="text-accent" /> : null}
        {briefing.generated_by === "gemini" ? "Drafted by Gemini" : "Drafted from template"} from crew notes and recorded vitals ·
        updated {freshness(briefing.generated_at, now)} · verify with the crew
      </p>
    </article>
  );
}
