import { twMerge } from "tailwind-merge";

import PillBase from "@/app/components/(pills)/PillBase";
import type { Transfer } from "@/lib/api";

const STATUS: Record<Transfer["status"], { label: string; tone: string }> = {
  pending: { label: "Awaiting acceptance", tone: "border-warn/40 bg-warn-soft text-warn" },
  accepted: { label: "Accepted", tone: "border-brand/40 bg-brand-soft text-brand-strong" },
  arrived: { label: "Arrived", tone: "border-brand bg-brand text-white" },
  closed: { label: "Closed", tone: "" },
};

export default function ({ status, className, ...props }: React.JSX.IntrinsicElements["span"] & { status: Transfer["status"] }) {
  const s = STATUS[status];
  return (
    <PillBase className={twMerge(s.tone, className)} {...props}>
      {s.label}
    </PillBase>
  );
}
