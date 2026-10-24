import { twMerge } from "tailwind-merge";

import type { Severity } from "@/lib/api";
import { SEVERITY_LABEL } from "@/lib/format";

import PillBase from "./PillBase";

const TONE: Record<Severity, string> = {
  low: "",
  low_medium: "border-warn bg-warn-soft text-warn-fg",
  medium: "border-warn bg-warn-soft text-warn-fg",
  high: "border-alert bg-alert-soft text-alert",
  critical: "border-alert bg-alert text-white",
};

export default function ({
  severity,
  className,
  ...props
}: React.JSX.IntrinsicElements["span"] & { severity?: Severity | null }) {
  if (!severity) return <PillBase className={className} {...props}>Unassessed</PillBase>;
  return (
    <PillBase className={twMerge(TONE[severity], className)} {...props}>
      {SEVERITY_LABEL[severity]}
    </PillBase>
  );
}
