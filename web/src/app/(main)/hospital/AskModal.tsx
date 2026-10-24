// Ask the crew a question — spoken aloud in the vehicle; the crew answers by voice.
"use client";

import { useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import ModalPrimary from "@/app/components/(modals)/ModalPrimary";
import { post, type Transfer } from "@/lib/api";
import { toastError } from "@/lib/toast";

import styles from "./Hospital.module.scss";

const SUGGESTIONS = [
  "Any allergies?",
  "Is the patient on blood thinners?",
  "Exact time symptoms started?",
  "Current pain score?",
  "Any change in consciousness?",
];

export default function ({ t, open, onClose, onDone }: { t: Transfer; open: boolean; onClose: () => void; onDone: (t: Transfer) => void }) {
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const send = async (question: string) => {
    setBusy(true);
    let sender: string | null = null;
    try {
      sender = localStorage.getItem("atollcare.clinician");
    } catch {
      sender = null;
    }
    try {
      onDone(await post<Transfer>(`/transfers/${t.id}/messages`, { text: question, kind: "question", sender: sender || null }));
      setText("");
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
      title="Ask the crew"
      footer={
        <>
          <ButtonBase onClick={onClose}>Cancel</ButtonBase>
          <ButtonPrimary onClick={() => send(text.trim())} disabled={busy || !text.trim()}>
            Send
          </ButtonPrimary>
        </>
      }
    >
      <div className={styles.chips}>
        {SUGGESTIONS.map((s) => (
          <button key={s} type="button" onClick={() => send(s)} disabled={busy}>
            {s}
          </button>
        ))}
      </div>
      <label className={styles.field}>
        <span>Or type a question</span>
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => e.key === "Enter" && text.trim() && send(text.trim())} autoFocus />
      </label>
      <p className="text-[0.875rem] text-muted">The question is read aloud in the vehicle; the answer appears here.</p>
    </ModalPrimary>
  );
}
