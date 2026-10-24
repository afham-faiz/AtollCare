import { twMerge } from "tailwind-merge";

import type { CaseStatus } from "@/lib/api";
import { STATUS_LABEL } from "@/lib/format";

import PillBase from "./PillBase";

const TONE: Partial<Record<CaseStatus, string>> = {
  needs_info: "border-warn bg-warn-soft text-warn-fg",
  declined: "border-alert bg-alert-soft text-alert",
  accepted: "border-brand bg-brand-soft text-brand",
  dispatched: "border-brand bg-brand-soft text-brand",
  in_transit: "border-brand bg-brand text-brand-fg",
  arrived: "border-brand bg-brand-soft text-brand",
};

export default function ({ status, className, ...props }: React.JSX.IntrinsicElements["span"] & { status: CaseStatus }) {
  return (
    <PillBase className={twMerge(TONE[status], className)} {...props}>
      {STATUS_LABEL[status]}
    </PillBase>
  );
}
