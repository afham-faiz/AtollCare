// F-M2.9 Headline metric — shown on every screen that has a case.
import { Clock } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { Case } from "@/lib/api";

export default function ({ headline, className, ...props }: React.JSX.IntrinsicElements["div"] & { headline: Case["headline"] }) {
  const saved = headline.saved_vs_baseline_min;
  return (
    <div
      className={twMerge(
        "flex items-start gap-[.75rem] rounded-[.75rem] border-[1px] border-brand bg-brand-soft px-[1rem] py-[.75rem]",
        className,
      )}
      {...props}
    >
      <Clock size={20} className="mt-[.125rem] shrink-0 text-brand" />
      <p className="text-[0.9375rem] font-medium tabular-nums">
        {headline.text}
        {saved !== null && saved !== undefined && (
          <span className="ml-[.5rem] text-[0.875rem] font-normal text-muted">(baseline = DEMO ASSUMPTION)</span>
        )}
      </p>
    </div>
  );
}
