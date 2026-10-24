// F-M1.8 Status stepper (submitted → referred → accepted → dispatched → in transit → arrived), advances via polling.
import { Check } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { CaseStatus } from "@/lib/api";

const STEPS: { id: CaseStatus; label: string }[] = [
  { id: "submitted", label: "Submitted" },
  { id: "referred", label: "Referred" },
  { id: "accepted", label: "Accepted" },
  { id: "dispatched", label: "Dispatched" },
  { id: "in_transit", label: "In transit" },
  { id: "arrived", label: "Arrived" },
];

const RANK: Record<CaseStatus, number> = {
  draft: -1,
  submitted: 0,
  assessed: 0,
  referred: 1,
  needs_info: 1,
  declined: 1,
  accepted: 2,
  dispatched: 3,
  in_transit: 4,
  arrived: 5,
  closed: 5,
};

export default function ({ status, className }: { status: CaseStatus; className?: string }) {
  const rank = RANK[status];
  return (
    // 3 × 2 grid in narrow columns, one row once the container is ≥ 30rem
    <div className={twMerge("@container", className)}>
      <ol className="grid grid-cols-3 gap-x-[.25rem] gap-y-[.75rem] @[30rem]:grid-cols-6">
        {STEPS.map((s, i) => {
          const done = i < rank || (i === rank && status === "arrived") || status === "closed";
          const current = i === rank && !done;
          return (
            <li key={s.id} className="flex flex-col items-center gap-[.25rem] text-center">
              <span
                className={twMerge(
                  "flex h-[1.75rem] w-[1.75rem] items-center justify-center rounded-[50%] border-[1px] border-border text-[0.875rem]",
                  done && "border-brand bg-brand text-brand-fg",
                  current && "border-brand text-brand animate-skeleton",
                )}
              >
                {done ? <Check size={16} /> : i + 1}
              </span>
              <span className={twMerge("text-[0.875rem] leading-tight text-muted", (done || current) && "text-fg")}>
                {s.label}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
