// F-M1.3 Patient details: collapsible form, tag inputs, PATCH on blur (SBAR picks it up on next generation).
"use client";

import { X } from "lucide-react";
import { useEffect, useState } from "react";

import PillBase from "@/app/components/(pills)/PillBase";
import { patch, type Case, type Patient } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";

import styles from "../Report.module.scss";

function TagInput({ label, value, onChange }: { label: string; value: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const v = draft.trim();
    if (v && !value.includes(v)) onChange([...value, v]);
    setDraft("");
  };
  return (
    <label className={styles.field}>
      <span>{label}</span>
      <div className="flex flex-wrap gap-[.375rem]">
        {value.map((t) => (
          <PillBase key={t}>
            {t}
            <button type="button" aria-label={`Remove ${t}`} onClick={() => onChange(value.filter((x) => x !== t))}>
              <X size={16} />
            </button>
          </PillBase>
        ))}
      </div>
      <input
        value={draft}
        placeholder="Type and press Enter"
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add();
          }
        }}
        onBlur={add}
      />
    </label>
  );
}

export default function ({ c }: { c: Case }) {
  const [p, setP] = useState<Patient>(c.patient);
  const { run } = useCaseAction(c.id);

  useEffect(() => setP(c.patient), [c.patient]);

  const save = (next: Patient) => {
    setP(next);
    if (JSON.stringify(next) === JSON.stringify(c.patient)) return;
    run(() => patch<Case>(`/cases/${c.id}`, { patient: next }));
  };

  return (
    <details className="rounded-[.75rem] border-[1px] border-border bg-raised p-[1rem]">
      <summary className="min-h-[2rem] cursor-pointer font-semibold">
        Patient details {p.age ? `· ${p.age}${p.sex ?? ""}` : ""}
      </summary>
      <div className="mt-[.75rem] grid grid-cols-2 gap-[.75rem]">
        <label className={`${styles.field} col-span-2`}>
          <span>Name</span>
          <input defaultValue={p.name ?? ""} onBlur={(e) => save({ ...p, name: e.target.value || null })} />
        </label>
        <label className={styles.field}>
          <span>Age</span>
          <input
            type="number"
            defaultValue={p.age ?? ""}
            onBlur={(e) => save({ ...p, age: e.target.value ? Number(e.target.value) : null })}
          />
        </label>
        <label className={styles.field}>
          <span>Sex</span>
          <select value={p.sex ?? ""} onChange={(e) => save({ ...p, sex: (e.target.value || null) as Patient["sex"] })}>
            <option value="">—</option>
            <option value="F">Female</option>
            <option value="M">Male</option>
            <option value="X">Other</option>
          </select>
        </label>
        <label className="col-span-2 flex min-h-[2.75rem] items-center gap-[.5rem] text-[0.875rem]">
          <input
            type="checkbox"
            checked={!!p.pregnant}
            onChange={(e) => save({ ...p, pregnant: e.target.checked })}
            className="h-[1.25rem] w-[1.25rem]"
          />
          Pregnant
        </label>
        <div className="col-span-2 flex flex-col gap-[.75rem]">
          <TagInput label="Known conditions" value={p.known_conditions ?? []} onChange={(v) => save({ ...p, known_conditions: v })} />
          <TagInput label="Medications" value={p.medications ?? []} onChange={(v) => save({ ...p, medications: v })} />
          <TagInput label="Allergies" value={p.allergies ?? []} onChange={(v) => save({ ...p, allergies: v })} />
        </div>
      </div>
    </details>
  );
}
