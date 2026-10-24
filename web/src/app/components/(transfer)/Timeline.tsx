// Transfer timeline: crew notes (with extracted interventions), hospital questions and answers, alerts, events.
import { AlertTriangle, Building2, CornerDownRight, HelpCircle, Mic, PenLine } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { Note } from "@/lib/api";
import { fmtTime } from "@/lib/format";

const ICON = {
  voice: Mic,
  text: PenLine,
  question: HelpCircle,
  message: Building2,
  answer: CornerDownRight,
  alert: AlertTriangle,
  event: null,
} as const;

const TONE: Record<string, string> = {
  question: "text-accent bg-accent-soft",
  message: "text-accent bg-accent-soft",
  answer: "text-teal-strong bg-teal-soft",
  alert: "text-critical bg-critical-soft",
  voice: "text-teal-strong bg-teal-soft",
  text: "text-teal-strong bg-teal-soft",
};

const WHO = { crew: "Crew", hospital: "Hospital", system: "AtollCare" } as const;

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
  if (!shown.length) return <p className={twMerge("text-ink-3", className)}>Nothing yet.</p>;
  return (
    <ol className={twMerge("flex flex-col", className)}>
      {shown.map((n, i) => {
        const Icon = ICON[n.kind];
        return (
          <li key={n.id} className="relative flex gap-[.875rem] pb-[1rem] last:pb-0">
            {i < shown.length - 1 && <span className="absolute bottom-0 left-[.8125rem] top-[1.75rem] w-[1px] bg-line" aria-hidden />}
            <span
              className={twMerge(
                "relative z-[1] mt-[.0625rem] flex h-[1.625rem] w-[1.625rem] shrink-0 items-center justify-center rounded-full",
                Icon ? TONE[n.kind] : "bg-transparent",
              )}
            >
              {Icon ? <Icon size={13} strokeWidth={2.4} /> : <span className="h-[.375rem] w-[.375rem] rounded-full bg-line-strong" />}
            </span>
            <div className="min-w-0 flex-1">
              <p className={twMerge("text-[0.9375rem] leading-[1.5]", n.kind === "event" && "text-ink-2", n.kind === "alert" && "font-[600] text-critical")}>
                {n.text}
              </p>
              {!!n.extraction?.interventions.length && (
                <div className="mt-[.375rem] flex flex-wrap gap-[.375rem]">
                  {n.extraction.interventions.map((x) => (
                    <span key={x} className="rounded-full bg-teal-soft px-[.625rem] py-[.125rem] text-[0.8125rem] font-[600] text-teal-strong">
                      {x}
                    </span>
                  ))}
                </div>
              )}
              <p className="tnum mt-[.125rem] text-[0.8125rem] text-ink-3">
                {fmtTime(n.at, tz)} · {WHO[n.author]}
              </p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
