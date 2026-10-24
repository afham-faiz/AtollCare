// Origin → destination, mode, and arrival — compact, one line, with an honest progress hairline.
import { twMerge } from "tailwind-merge";

import type { Region, Transfer } from "@/lib/api";
import { fmtMin, fmtTime, MODE_LABEL, minutesUntil, place } from "@/lib/format";

import ModeIcon from "./ModeIcon";

export default function ({
  t,
  region,
  now,
  align = "left",
  className,
}: {
  t: Transfer;
  region?: Region;
  now?: string;
  align?: "left" | "right";
  className?: string;
}) {
  const left = minutesUntil(t.eta, now);
  const done = t.status === "arrived" || t.status === "closed";
  return (
    <div className={twMerge("flex min-w-0 flex-col gap-[.375rem]", align === "right" && "items-end text-right", className)}>
      <span className="flex min-w-0 items-center gap-[.5rem] text-[0.9375rem] text-ink-2">
        <ModeIcon mode={t.mode} size={16} className="shrink-0 text-ink-3" />
        <span className="truncate">
          {place(region, t.origin_id)} <span className="text-ink-3">→</span> <span className="font-[600] text-ink">{place(region, t.destination_id)}</span>
        </span>
      </span>
      <span className="tnum text-[0.875rem] text-ink-2">
        {done ? (
          <>Arrived {fmtTime(t.arrived_at, region?.timezone)}</>
        ) : (
          <>
            {MODE_LABEL[t.mode]} · ETA <span className="font-[600] text-ink">{fmtTime(t.eta, region?.timezone)}</span>
            {left !== null && <span> · {fmtMin(left)}</span>}
          </>
        )}
      </span>
    </div>
  );
}
