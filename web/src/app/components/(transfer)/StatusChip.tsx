// Transfer workflow state, from the point of view of the screen showing it. Icon + words, never colour alone.
import { Check, Clock3, Flag, Send } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { TransferStatus } from "@/lib/api";

// a plain dot while it's still being prepared; icons once something has happened
function Dot({ className }: { className?: string }) {
  return <span className={twMerge("mx-[.25rem] h-[.375rem] w-[.375rem] rounded-full bg-current opacity-60", className)} aria-hidden />;
}

const STATES: Record<TransferStatus, { crew: string; hospital: string; icon: typeof Check | typeof Dot; cls: string }> = {
  preparing: { crew: "Preparing handoff", hospital: "Preparing", icon: Dot, cls: "bg-well text-ink-2" },
  pending: { crew: "Handoff sent", hospital: "Awaiting your response", icon: Clock3, cls: "bg-accent-soft text-accent-strong" },
  accepted: { crew: "Accepted", hospital: "Accepted", icon: Check, cls: "bg-[var(--sage-100)] text-[var(--sage-700)]" },
  arrived: { crew: "Arrived", hospital: "Arrived", icon: Flag, cls: "bg-pine text-white" },
  closed: { crew: "Closed", hospital: "Closed", icon: Send, cls: "bg-well text-ink-3" },
};

export default function ({
  status,
  view,
  className,
}: {
  status: TransferStatus;
  view: "crew" | "hospital";
  className?: string;
}) {
  const s = STATES[status];
  const Icon = s.icon;
  return (
    <span
      className={twMerge(
        "inline-flex items-center gap-[.375rem] whitespace-nowrap rounded-full py-[.3125rem] pl-[.625rem] pr-[.875rem] text-[0.8125rem] font-[500]",
        s.cls,
        className,
      )}
    >
      <Icon size={14} strokeWidth={1.75} className="shrink-0" />
      {s[view]}
    </span>
  );
}
