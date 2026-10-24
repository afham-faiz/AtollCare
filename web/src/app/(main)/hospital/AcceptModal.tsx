// Accept the transfer and say what's being prepared — read aloud in the vehicle.
"use client";

import { Check } from "lucide-react";
import { useEffect, useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import ModalPrimary from "@/app/components/(modals)/ModalPrimary";
import { post, type Transfer } from "@/lib/api";
import { toastError } from "@/lib/toast";

import styles from "./Hospital.module.scss";

const NAME_KEY = "atollcare.clinician";

export default function ({
  t,
  open,
  options,
  onClose,
  onDone,
}: {
  t: Transfer;
  open: boolean;
  options: string[];
  onClose: () => void;
  onDone: (t: Transfer) => void;
}) {
  const [by, setBy] = useState("");
  const [prepare, setPrepare] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!open) return;
    try {
      // restore the remembered clinician name when the dialog opens
      setBy(localStorage.getItem(NAME_KEY) ?? "");
    } catch {
      // storage unavailable
    }
  }, [open]);

  const submit = async () => {
    setBusy(true);
    try {
      localStorage.setItem(NAME_KEY, by);
    } catch {
      // storage unavailable
    }
    try {
      onDone(await post<Transfer>(`/transfers/${t.id}/accept`, { by, prepare, message: message || null }));
      onClose();
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
      title="Accept transfer"
      subtitle="Your response is read aloud to the crew"
      footer={
        <>
          <ButtonBase onClick={onClose}>Cancel</ButtonBase>
          <ButtonPrimary onClick={submit} disabled={busy || !by.trim()}>
            <Check size={18} /> Accept
          </ButtonPrimary>
        </>
      }
    >
      <label className={field.field}>
        <span className={field.label}>Accepting clinician</span>
        <input className={field.input} value={by} onChange={(e) => setBy(e.target.value)} placeholder="Dr … , Cardiology" autoFocus />
      </label>
      <div className={field.field}>
        <span className={field.label}>Preparing</span>
        <div className={styles.chips}>
          {options.map((o) => (
            <button key={o} type="button" aria-pressed={prepare.includes(o)} onClick={() => setPrepare((p) => (p.includes(o) ? p.filter((x) => x !== o) : [...p, o]))}>
              {o}
            </button>
          ))}
        </div>
      </div>
      <label className={field.field}>
        <span className={field.label}>Message to the crew</span>
        <input className={field.input} value={message} onChange={(e) => setMessage(e.target.value)} placeholder="Optional — e.g. come straight to resus bay 2" />
      </label>
    </ModalPrimary>
  );
}
