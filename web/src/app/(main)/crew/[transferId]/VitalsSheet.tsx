// What the camera can't measure: SpO₂, blood pressure, temperature, ACVPU, oxygen. Completes NEWS2.
"use client";

import { useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import Segmented from "@/app/components/(controls)/Segmented";
import ModalPrimary from "@/app/components/(modals)/ModalPrimary";
import { post, type VitalsRequest } from "@/lib/api";
import { toastError } from "@/lib/toast";

type Acvpu = "A" | "C" | "V" | "P" | "U";

export default function ({ transferId, open, onClose, onSaved }: { transferId: string; open: boolean; onClose: () => void; onSaved: () => void }) {
  const [spo2, setSpo2] = useState("");
  const [sbp, setSbp] = useState("");
  const [temp, setTemp] = useState("");
  const [acvpu, setAcvpu] = useState<Acvpu | null>(null);
  const [oxygen, setOxygen] = useState<"air" | "oxygen">("air");
  const [busy, setBusy] = useState(false);

  const save = async () => {
    const body: VitalsRequest = { source: "manual", on_oxygen: oxygen === "oxygen" };
    if (spo2) body.spo2 = Number(spo2);
    if (sbp) body.systolic_bp = Number(sbp);
    if (temp) body.temperature_c = Number(temp);
    if (acvpu) body.consciousness = acvpu;
    setBusy(true);
    try {
      await post(`/transfers/${transferId}/vitals`, body);
      onSaved();
      onClose();
      setSpo2("");
      setSbp("");
      setTemp("");
      setAcvpu(null);
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
    }
  };

  const numberField = (label: string, value: string, set: (v: string) => void, props: React.JSX.IntrinsicElements["input"]) => (
    <label className={field.field}>
      <span className={field.label}>{label}</span>
      <input className={`${field.input} tnum`} type="number" value={value} onChange={(e) => set(e.target.value)} {...props} />
    </label>
  );

  return (
    <ModalPrimary
      open={open}
      onClose={onClose}
      title="Crew vitals"
      subtitle="Values the camera can't measure"
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
        {numberField("SpO₂ %", spo2, setSpo2, { inputMode: "numeric", min: 50, max: 100, autoFocus: true })}
        {numberField("Systolic BP", sbp, setSbp, { inputMode: "numeric", min: 40, max: 280 })}
        {numberField("Temp °C", temp, setTemp, { inputMode: "decimal", step: "0.1", min: 30, max: 44 })}
      </div>
      <div className={field.field}>
        <span className={field.label}>Breathing</span>
        <Segmented
          label="Air or oxygen"
          value={oxygen}
          onChange={setOxygen}
          options={[
            { value: "air", label: "Room air" },
            { value: "oxygen", label: "On oxygen" },
          ]}
        />
      </div>
      <div className={field.field}>
        <span className={field.label}>Consciousness (ACVPU)</span>
        <Segmented
          label="ACVPU"
          value={acvpu}
          onChange={setAcvpu}
          className="w-full"
          options={[
            { value: "A", label: "Alert" },
            { value: "C", label: "Confused" },
            { value: "V", label: "Voice" },
            { value: "P", label: "Pain" },
            { value: "U", label: "None" },
          ]}
        />
      </div>
    </ModalPrimary>
  );
}
