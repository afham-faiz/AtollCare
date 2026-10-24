// Origin → destination, ETA and a progress bar. Used on both screens.
import { twMerge } from "tailwind-merge";

import type { Region, Transfer } from "@/lib/api";
import { fmtMin, fmtTime, MODE_LABEL, minutesUntil, place } from "@/lib/format";

import ModeIcon from "./ModeIcon";

export default function ({ t, region, now, className }: { t: Transfer; region?: Region; now?: string; className?: string }) {
  const left = minutesUntil(t.eta, now);
  const done = t.status === "arrived" || t.status === "closed";
  return (
    <div className={twMerge("flex flex-col gap-[.5rem]", className)}>
      <div className="flex flex-wrap items-baseline justify-between gap-x-[1rem] gap-y-[.25rem]">
        <span className="flex items-center gap-[.5rem] text-[0.9375rem]">
          <ModeIcon mode={t.mode} className="text-brand" />
          <span className="text-muted">{place(region, t.origin_id)}</span>
          <span aria-hidden>→</span>
          <strong>{place(region, t.destination_id)}</strong>
          <span className="hidden text-muted md:inline">· {MODE_LABEL[t.mode]}</span>
        </span>
        <span className="text-[0.9375rem] tabular-nums">
          {done ? (
            <strong>Arrived {fmtTime(t.arrived_at, region?.timezone)}</strong>
          ) : (
            <>
              ETA <strong>{fmtTime(t.eta, region?.timezone)}</strong>
              {left !== null && <span className="text-muted"> · {fmtMin(left)}</span>}
            </>
          )}
        </span>
      </div>
      <div className="h-[.375rem] overflow-hidden rounded-[1rem] bg-subtle" role="progressbar" aria-valuenow={Math.round(t.progress * 100)}>
        <div className="h-full rounded-[1rem] bg-brand transition-[width] duration-1000" style={{ width: `${t.progress * 100}%` }} />
      </div>
    </div>
  );
}
