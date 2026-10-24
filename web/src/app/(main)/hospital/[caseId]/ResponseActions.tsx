// F-M3.3 Accept / Decline / Request info. Accept needs responder name (remembered); decline needs a reason;
// needs-info pre-fills questions from intake.missing_info.
"use client";

import { Check, HelpCircle, X } from "lucide-react";
import { useEffect, useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonDanger from "@/app/components/(buttons)/ButtonDanger";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import ModalPrimary from "@/app/components/(modals)/ModalPrimary";
import { post, type Case } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";

import styles from "../Hospital.module.scss";

const NAME_KEY = "atollcare.responder";

export default function ({ c }: { c: Case }) {
  const [modal, setModal] = useState<null | "accepted" | "declined" | "needs_info">(null);
  const [name, setName] = useState("");
  const [note, setNote] = useState("");
  const [questions, setQuestions] = useState<Record<string, boolean>>({});
  const [custom, setCustom] = useState("");
  const { busy, run } = useCaseAction(c.id);

  useEffect(() => {
    try {
      setName(localStorage.getItem(NAME_KEY) ?? "");
    } catch {
      // ignore
    }
  }, []);

  const pending = c.status === "referred" || c.status === "needs_info";
  if (!pending) return null;

  const open = (m: typeof modal) => {
    setNote("");
    setCustom("");
    setQuestions(Object.fromEntries((c.intake?.missing_info ?? []).map((q) => [q, true])));
    setModal(m);
  };

  const submit = async () => {
    try {
      localStorage.setItem(NAME_KEY, name);
    } catch {
      // ignore
    }
    const info = [...Object.entries(questions).filter(([, v]) => v).map(([q]) => q), ...(custom.trim() ? [custom.trim()] : [])];
    const res = await run(() =>
      post<Case>(`/cases/${c.id}/referral/respond`, {
        response: modal,
        responder_name: name,
        note: note || null,
        info_requests: modal === "needs_info" ? info : [],
      }),
    );
    if (res) setModal(null);
  };

  const valid =
    name.trim() &&
    (modal !== "declined" || note.trim()) &&
    (modal !== "needs_info" || Object.values(questions).some(Boolean) || custom.trim());

  return (
    <>
      <div className={styles.actions}>
        <ButtonPrimary onClick={() => open("accepted")} className="flex-1">
          <Check size={20} /> Accept
        </ButtonPrimary>
        <ButtonBase onClick={() => open("needs_info")} className="flex-1">
          <HelpCircle size={20} /> Request info
        </ButtonBase>
        <ButtonDanger onClick={() => open("declined")} className="flex-1">
          <X size={20} /> Decline
        </ButtonDanger>
      </div>
      <ModalPrimary
        open={modal !== null}
        onClose={() => setModal(null)}
        title={modal === "accepted" ? "Accept referral" : modal === "declined" ? "Decline referral" : "Request more information"}
        footer={
          <>
            <ButtonBase onClick={() => setModal(null)}>Cancel</ButtonBase>
            {modal === "declined" ? (
              <ButtonDanger onClick={submit} disabled={!valid || busy}>Decline & re-route</ButtonDanger>
            ) : (
              <ButtonPrimary onClick={submit} disabled={!valid || busy}>
                {modal === "accepted" ? "Accept" : "Send questions"}
              </ButtonPrimary>
            )}
          </>
        }
      >
        <label className={styles.field}>
          <span>Your name & role</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Dr. … (Cardiology)" />
        </label>
        {modal === "needs_info" && (
          <div className="flex flex-col gap-[.25rem]">
            <p className="text-[0.875rem] text-muted">Suggested questions</p>
            {Object.keys(questions).map((q) => (
              <label key={q} className="flex min-h-[2.75rem] items-center gap-[.5rem]">
                <input
                  type="checkbox"
                  checked={questions[q]}
                  onChange={(e) => setQuestions((s) => ({ ...s, [q]: e.target.checked }))}
                  className="h-[1.25rem] w-[1.25rem]"
                />
                {q}
              </label>
            ))}
            <label className={styles.field}>
              <span>Custom question</span>
              <input value={custom} onChange={(e) => setCustom(e.target.value)} />
            </label>
          </div>
        )}
        <label className={styles.field}>
          <span>{modal === "declined" ? "Reason (required)" : "Note (optional)"}</span>
          <textarea value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        {modal === "declined" && (
          <p className="text-[0.875rem] text-muted">The engine will exclude this hospital, re-plan and re-send the referral automatically.</p>
        )}
      </ModalPrimary>
    </>
  );
}
