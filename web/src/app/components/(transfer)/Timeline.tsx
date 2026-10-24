// Transfer timeline: crew notes (with extracted interventions), hospital questions/answers, alerts, events.
import { AlertTriangle, Building2, CircleDot, CornerDownRight, HelpCircle, Mic, PenLine } from "lucide-react";
import { twMerge } from "tailwind-merge";

import PillBase from "@/app/components/(pills)/PillBase";
import type { Note } from "@/lib/api";
import { fmtTime } from "@/lib/format";

const ICON = {
  voice: Mic,
  text: PenLine,
  question: HelpCircle,
  message: Building2,
  answer: CornerDownRight,
  alert: AlertTriangle,
  event: CircleDot,
} as const;

const TONE: Record<string, string> = {
  question: "text-info",
  message: "text-info",
  answer: "text-brand",
  alert: "text-alert",
  event: "text-faint",
  voice: "text-brand",
  text: "text-brand",
};

export default function ({
  notes,
  tz,
  limit,
  newestFirst = true,
  className,
}: {
  notes: Note[];
  tz?: string;
  limit?: number;
  newestFirst?: boolean;
  className?: string;
}) {
  const ordered = newestFirst ? [...notes].reverse() : notes;
  const shown = limit ? ordered.slice(0, limit) : ordered;
  if (!shown.length) return <p className={twMerge("text-muted", className)}>Nothing yet.</p>;
  return (
    <ol className={twMerge("flex flex-col gap-[.875rem]", className)}>
      {shown.map((n) => {
        const Icon = ICON[n.kind];
        return (
          <li key={n.id} className="flex gap-[.75rem]">
            <Icon size={18} className={twMerge("mt-[.125rem] shrink-0", TONE[n.kind])} />
            <div className="min-w-0 flex-1">
              <p className={twMerge("text-[0.9375rem]", n.kind === "event" && "text-muted", n.kind === "alert" && "font-medium")}>
                {n.text}
              </p>
              {!!n.extraction?.interventions.length && (
                <div className="mt-[.375rem] flex flex-wrap gap-[.375rem]">
                  {n.extraction.interventions.map((i) => (
                    <PillBase key={i} className="border-brand/30 bg-brand-soft text-brand-strong">
                      {i}
                    </PillBase>
                  ))}
                </div>
              )}
              <p className="mt-[.125rem] text-[0.875rem] text-faint tabular-nums">
                {fmtTime(n.at, tz)} · {n.author === "crew" ? "Crew" : n.author === "hospital" ? "Hospital" : "System"}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
