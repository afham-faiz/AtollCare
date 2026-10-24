// F-M4.6 Asset roster with status toggles; taking the only seaplane offline re-plans non-dispatched cases.
"use client";

import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ModeIcon from "@/app/components/(case)/ModeIcon";
import Card from "@/app/components/Card";
import { patch, type Facility, type TransportAsset } from "@/lib/api";
import { facilityName, MODE_LABEL } from "@/lib/format";
import { useAssets } from "@/lib/swr";
import { toast, toastError } from "@/lib/toast";

const STATUSES = ["available", "busy", "offline"] as const;

export default function ({ facilities }: { facilities: Facility[] }) {
  const { data } = useAssets();
  const set = async (a: TransportAsset, status: TransportAsset["status"]) => {
    try {
      await patch(`/transport/assets/${a.id}`, { status });
      await mutate("/transport/assets");
      toast(`${a.id} → ${status}; open cases re-assessed`);
    } catch (err) {
      toastError(err);
    }
  };
  const order = ["seaplane", "fixed_wing", "helicopter", "sea_ambulance", "speedboat"];
  const assets = [...(data ?? [])].sort((a, b) => order.indexOf(a.mode) - order.indexOf(b.mode) || a.id.localeCompare(b.id));
  return (
    <Card title="Asset roster">
      <ul className="flex max-h-[32rem] flex-col gap-[.25rem] overflow-y-auto">
        {assets.map((a) => (
          <li key={a.id} className="flex items-center gap-[.5rem] border-b-[1px] border-border py-[.375rem] text-[0.875rem]">
            <ModeIcon mode={a.mode} className="shrink-0 text-brand" />
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{MODE_LABEL[a.mode]} · {facilityName(facilities, a.home_facility_id)}</span>
              <span className="block truncate text-muted">{a.id}</span>
            </span>
            <select
              value={a.status}
              onChange={(e) => set(a, e.target.value as TransportAsset["status"])}
              aria-label={`Status of ${a.id}`}
              className={twMerge(
                "h-[2.5rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.375rem]",
                a.status === "busy" && "text-warn-fg",
                a.status === "offline" && "text-alert",
              )}
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </li>
        ))}
      </ul>
    </Card>
  );
}
