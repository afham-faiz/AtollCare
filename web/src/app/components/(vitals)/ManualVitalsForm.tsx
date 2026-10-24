// F-M1.4 Manual vitals: HR, RR, SpO₂, on O₂, SBP, temp, ACVPU.
"use client";

import { useState } from "react";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import type { ManualVitalsRequest } from "@/lib/api";

import styles from "./Vitals.module.scss";

const FIELDS: { key: keyof ManualVitalsRequest; label: string; step?: string; min: number; max: number }[] = [
  { key: "heart_rate", label: "Heart rate /min", min: 20, max: 250 },
  { key: "resp_rate", label: "Resp rate /min", min: 4, max: 70 },
  { key: "spo2", label: "SpO₂ %", min: 50, max: 100 },
  { key: "systolic_bp", label: "Systolic BP", min: 40, max: 280 },
  { key: "temperature_c", label: "Temp °C", step: "0.1", min: 30, max: 44 },
];

export default function ({
  onSubmit,
  busy,
}: {
  onSubmit: (req: ManualVitalsRequest) => Promise<void> | void;
  busy?: boolean;
}) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [onOxygen, setOnOxygen] = useState(false);
  const [acvpu, setAcvpu] = useState("");

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const req: ManualVitalsRequest = { source: "manual", on_oxygen: onOxygen };
    for (const f of FIELDS) {
      const v = values[f.key as string];
      if (v !== undefined && v !== "") (req as Record<string, unknown>)[f.key] = Number(v);
    }
    if (acvpu) req.consciousness = acvpu as ManualVitalsRequest["consciousness"];
    await onSubmit(req);
    setValues({});
  };

  return (
    <form onSubmit={submit} className="flex flex-col gap-[.75rem]">
      <div className="grid grid-cols-2 gap-[.75rem] sm:grid-cols-3">
        {FIELDS.map((f) => (
          <label key={f.key} className={styles.field}>
            <span>{f.label}</span>
            <input
              type="number"
              inputMode="decimal"
              step={f.step ?? "1"}
              min={f.min}
              max={f.max}
              value={values[f.key as string] ?? ""}
              onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
            />
          </label>
        ))}
        <label className={styles.field}>
          <span>ACVPU</span>
          <select value={acvpu} onChange={(e) => setAcvpu(e.target.value)}>
            <option value="">—</option>
            <option value="A">A — Alert</option>
            <option value="C">C — New confusion</option>
            <option value="V">V — Voice</option>
            <option value="P">P — Pain</option>
            <option value="U">U — Unresponsive</option>
          </select>
        </label>
      </div>
      <label className="flex min-h-[2.75rem] items-center gap-[.5rem]">
        <input type="checkbox" checked={onOxygen} onChange={(e) => setOnOxygen(e.target.checked)} className="h-[1.25rem] w-[1.25rem]" />
        On supplemental oxygen
      </label>
      <ButtonPrimary type="submit" disabled={busy}>
        Save vitals
      </ButtonPrimary>
    </form>
  );
}
