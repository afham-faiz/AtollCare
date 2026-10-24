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
            {id.needs_review ? <ShieldAlert size={16} /> : <ShieldCheck size={16} />}
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
      <button type="button" className={styles.photoBtn} onClick={() => input.current?.click()} disabled={busy}>
        {busy ? <Loader2 size={18} className="animate-spin" /> : <CreditCard size={18} />}
        {busy ? "Reading the card…" : id ? "Take another photo" : "Take a photo of their ID"}
      </button>
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
