import { AlertTriangle } from "lucide-react";
import { twMerge } from "tailwind-merge";

import type { Alert } from "@/lib/api";

export default function ({ alerts, className }: { alerts: Alert[]; className?: string }) {
  if (!alerts.length) return null;
  const critical = alerts.some((a) => a.level === "critical");
  return (
    <div
      role="alert"
      className={twMerge(
        "flex items-start gap-[.75rem] rounded-[.75rem] px-[1rem] py-[.75rem] font-medium",
        critical ? "bg-alert text-white" : "border-[1px] border-warn/40 bg-warn-soft text-warn",
        className,
      )}
    >
      <AlertTriangle size={20} className="mt-[.125rem] shrink-0" />
      <span>{alerts.map((a) => a.text).join(" · ")}</span>
    </div>
  );
}
