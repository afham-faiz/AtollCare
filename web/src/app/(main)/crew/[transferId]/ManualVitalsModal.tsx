// The values a camera can't measure: SpO₂, blood pressure, temperature, ACVPU, oxygen. Completes NEWS2.
"use client";

import { useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import ModalPrimary from "@/app/components/(modals)/ModalPrimary";
import { post, type VitalsRequest } from "@/lib/api";
import { toastError } from "@/lib/toast";

import styles from "../Crew.module.scss";

const ACVPU = [
  { v: "A", label: "Alert" },
  { v: "C", label: "Confused" },
  { v: "V", label: "Voice" },
  { v: "P", label: "Pain" },
  { v: "U", label: "Unresp." },
] as const;

export default function ({ transferId, open, onClose, onSaved }: { transferId: string; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [spo2, setSpo2] = useState("");
  const [sbp, setSbp] = useState("");
  const [temp, setTemp] = useState("");
  const [acvpu, setAcvpu] = useState<string>("");
  const [oxygen, setOxygen] = useState(false);
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const body: VitalsRequest = { source: "manual", on_oxygen: oxygen };
    if (spo2) body.spo2 = Number(spo2);
    if (sbp) body.systolic_bp = Number(sbp);
    if (temp) body.temperature_c = Number(temp);
    if (acvpu) body.consciousness = acvpu as VitalsRequest["consciousness"];
    setBusy(true);
    try {
      await post(`/transfers/${transferId}/vitals`, body);
      onSaved();
      onClose();
      setSpo2("");
      setSbp("");
      setTemp("");
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalPrimary
      open={open}
      onClose={onClose}
      title="Add vitals"
      footer={
        <>
          <ButtonBase onClick={onClose}>Cancel</ButtonBase>
          <ButtonPrimary onClick={save} disabled={busy || (!spo2 && !sbp && !temp && !acvpu)}>
            Save
          </ButtonPrimary>
        </>
      }
    >
      <div className="grid grid-cols-3 gap-[.75rem]">
        <label className={styles.field}>
          <span>SpO₂ %</span>
          <input type="number" inputMode="numeric" min={50} max={100} value={spo2} onChange={(e) => setSpo2(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>Systolic BP</span>
          <input type="number" inputMode="numeric" min={40} max={280} value={sbp} onChange={(e) => setSbp(e.target.value)} />
        </label>
        <label className={styles.field}>
          <span>Temp °C</span>
          <input type="number" inputMode="decimal" step="0.1" min={30} max={44} value={temp} onChange={(e) => setTemp(e.target.value)} />
        </label>
      </div>
      <div className={styles.field}>
        <span>Consciousness (ACVPU)</span>
        <div className={styles.segmented}>
          {ACVPU.map((a) => (
            <button key={a.v} type="button" aria-pressed={acvpu === a.v} onClick={() => setAcvpu(acvpu === a.v ? "" : a.v)}>
              <strong>{a.v}</strong> {a.label}
            </button>
          ))}
        </div>
      </div>
      <label className="flex min-h-[2.75rem] items-center gap-[.5rem]">
        <input type="checkbox" checked={oxygen} onChange={(e) => setOxygen(e.target.checked)} className="h-[1.25rem] w-[1.25rem] accent-[var(--brand)]" />
        On supplemental oxygen
      </label>
    </ModalPrimary>
  );
}
