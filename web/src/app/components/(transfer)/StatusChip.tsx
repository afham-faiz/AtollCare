// Transfer workflow state, from the point of view of the screen showing it. Icon + words, never colour alone.
import { Check, CircleDashed, Clock3, Flag, Send } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { TransferStatus } from "@/lib/api";

const STATES: Record<TransferStatus, { crew: string; hospital: string; icon: typeof Check; cls: string }> = {
  preparing: { crew: "Preparing handoff", hospital: "Preparing", icon: CircleDashed, cls: "bg-well text-ink-2" },
  pending: { crew: "Handoff sent", hospital: "Awaiting your response", icon: Clock3, cls: "bg-accent-soft text-accent-strong" },
  accepted: { crew: "Accepted", hospital: "Accepted", icon: Check, cls: "bg-teal-soft text-teal-strong" },
  arrived: { crew: "Arrived", hospital: "Arrived", icon: Flag, cls: "bg-teal text-white" },
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
        "inline-flex items-center gap-[.375rem] whitespace-nowrap rounded-full py-[.25rem] pl-[.5rem] pr-[.75rem] text-[0.8125rem] font-[600]",
        s.cls,
        className,
      )}
    >
      <Icon size={14} strokeWidth={2.4} />
      {s[view]}
    </span>
  );
}
