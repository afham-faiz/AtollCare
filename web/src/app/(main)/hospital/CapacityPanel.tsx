// F-M3.8 Capacity panel: ICU beds, cath lab, CT, blood units. Changes re-assess open cases (visible re-plan).
"use client";

import { mutate } from "swr";

import Card from "@/app/components/Card";
import SourceBadge from "@/app/components/SourceBadge";
import { patch, type Facility, type HospitalCapacity } from "@/lib/api";
import { facilityName } from "@/lib/format";
import { useCapacity } from "@/lib/swr";
import { toast, toastError } from "@/lib/toast";

function Toggle({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex min-h-[2.75rem] items-center justify-between gap-[.5rem] text-[0.875rem]">
      {label}
      <input type="checkbox" role="switch" checked={value} onChange={(e) => onChange(e.target.checked)} className="h-[1.25rem] w-[1.25rem] accent-[var(--brand)]" />
    </label>
  );
}

export default function ({ facilities, focusId }: { facilities: Facility[]; focusId?: string }) {
  const { data } = useCapacity();
  const update = async (id: string, body: Partial<HospitalCapacity>) => {
    try {
      await patch(`/hospitals/${id}/capacity`, body);
      await mutate("/hospitals/capacity");
      toast(`${facilityName(facilities, id)} capacity updated — open cases re-assessed`);
    } catch (err) {
      toastError(err);
    }
  };
  const rows = [...(data ?? [])].sort((a, b) => (a.facility_id === focusId ? -1 : b.facility_id === focusId ? 1 : 0));
  return (
    <Card title="Capacity" aside={<SourceBadge kind="assumption" />}>
      <div className="flex flex-col gap-[.75rem]">
        {rows.map((c) => (
          <details key={c.facility_id} open={c.facility_id === focusId} className="rounded-[.5rem] border-[1px] border-border p-[.75rem]">
            <summary className="cursor-pointer font-medium">{facilityName(facilities, c.facility_id)}</summary>
            <div className="mt-[.5rem] flex flex-col">
              {c.cath_lab_available !== null && c.cath_lab_available !== undefined && (
                <Toggle label="Cath lab available" value={c.cath_lab_available} onChange={(v) => update(c.facility_id, { cath_lab_available: v })} />
              )}
              {c.ct_available !== null && c.ct_available !== undefined && (
                <Toggle label="CT available" value={c.ct_available} onChange={(v) => update(c.facility_id, { ct_available: v })} />
              )}
              {c.icu_beds_free !== null && c.icu_beds_free !== undefined && (
                <label className="flex min-h-[2.75rem] items-center justify-between text-[0.875rem]">
                  ICU beds free
                  <input
                    type="number"
                    min={0}
                    defaultValue={c.icu_beds_free}
                    onBlur={(e) => Number(e.target.value) !== c.icu_beds_free && update(c.facility_id, { icu_beds_free: Number(e.target.value) })}
                    className="h-[2.5rem] w-[5rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.5rem] tabular-nums"
                  />
                </label>
              )}
              {c.blood_bank_units !== null && c.blood_bank_units !== undefined && (
                <label className="flex min-h-[2.75rem] items-center justify-between text-[0.875rem]">
                  Blood units
                  <input
                    type="number"
                    min={0}
                    defaultValue={c.blood_bank_units}
                    onBlur={(e) => Number(e.target.value) !== c.blood_bank_units && update(c.facility_id, { blood_bank_units: Number(e.target.value) })}
                    className="h-[2.5rem] w-[5rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.5rem] tabular-nums"
                  />
                </label>
              )}
            </div>
          </details>
        ))}
      </div>
    </Card>
  );
}
