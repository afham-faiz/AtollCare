// Step 3 (optional): a photo of the patient's ID. Gemini reads only what is printed; unclear fields stay blank and the
// card is marked "check by eye". Age comes from the date of birth, worked out in code.
"use client";

import { CreditCard, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { useRef, useState } from "react";

import { api, type Intake } from "@/lib/api";
import { toastError } from "@/lib/toast";

import styles from "../PreArrival.module.scss";

export default function ({ intake, onSaved }: { intake: Intake; onSaved: (i: Intake) => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const id = intake.identity;

  const upload = async (file: File) => {
    setBusy(true);
    const form = new FormData();
    form.append("image", file, file.name || "id.jpg");
    try {
      onSaved(await api<Intake>(`/intakes/${intake.id}/id-photo`, { method: "POST", body: form }));
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
    }
  };

  const rows = id
    ? ([
        ["Name", id.full_name],
        ["Date of birth", id.date_of_birth],
        ["Age", id.age != null ? String(id.age) : null],
        ["ID number", id.id_number],
        ["Document", id.document_type],
      ] as const)
    : [];

  return (
    <div className={styles.stack}>
      {id && (
        <div className={styles.idCard}>
          <p className={id.needs_review ? styles.review : styles.clear}>
            {id.needs_review ? <ShieldAlert size={16} strokeWidth={1.75} /> : <ShieldCheck size={16} strokeWidth={1.75} />}
            {id.needs_review ? "Check by eye at the health centre" : "Read clearly"}
          </p>
          <dl>
            {rows.map(([k, v]) => (
              <div key={k}>
                <dt>{k}</dt>
                <dd className={v ? "" : "text-ink-3"}>{v ?? "Not read"}</dd>
              </div>
            ))}
          </dl>
          {id.issues.length > 0 && <p className="text-[0.8125rem] text-ink-3">{id.issues.slice(0, 2).join(" · ")}</p>}
        </div>
      )}
      {id ? (
        <button type="button" className={styles.photoAgain} onClick={() => input.current?.click()} disabled={busy}>
          {busy ? <Loader2 size={18} strokeWidth={1.75} className="animate-spin" /> : <CreditCard size={18} strokeWidth={1.75} />}
          {busy ? "Reading the card" : "Take another photo"}
        </button>
      ) : (
        <button type="button" className={styles.idFrame} onClick={() => input.current?.click()} disabled={busy}>
          <svg className={styles.idGuide} viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden>
            <path d="M6 22 V10 Q6 6 10 6 H22" />
            <path d="M94 22 V10 Q94 6 90 6 H78" />
            <path d="M6 78 V90 Q6 94 10 94 H22" />
            <path d="M94 78 V90 Q94 94 90 94 H78" />
          </svg>
          <span className={styles.idShutter}>{busy ? <Loader2 size={22} strokeWidth={1.75} className="animate-spin" /> : <CreditCard size={22} strokeWidth={1.75} />}</span>
          <span className={styles.idFrameText}>{busy ? "Reading the card" : "Tap to photograph their ID"}</span>
        </button>
      )}
      <input
        ref={input}
        type="file"
        accept="image/*"
        capture="environment"
        hidden
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload(f);
          e.target.value = "";
        }}
      />
    </div>
  );
}
