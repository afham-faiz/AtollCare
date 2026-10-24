// F-M1.9 Respond to specialist info requests.
"use client";

import { MessageCircleQuestion } from "lucide-react";
import { useState } from "react";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import { post, type Case } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";

import styles from "../Report.module.scss";

export default function ({ c }: { c: Case }) {
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const { busy, run } = useCaseAction(c.id);
  const questions = c.referral?.info_requests ?? [];
  if (c.status !== "needs_info" || questions.length === 0) return null;
  return (
    <section className="rounded-[.75rem] border-[2px] border-warn bg-warn-soft p-[1rem]">
      <h2 className="mb-[.75rem] flex items-center gap-[.5rem] font-semibold text-warn-fg">
        <MessageCircleQuestion size={20} /> The specialist needs more information
      </h2>
      <div className="flex flex-col gap-[.75rem]">
        {questions.map((q) => (
          <label key={q} className={styles.field}>
            <span className="text-fg">{q}</span>
            <input value={answers[q] ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [q]: e.target.value }))} />
          </label>
        ))}
        <ButtonPrimary
          disabled={busy || !Object.values(answers).some((a) => a.trim())}
          onClick={() => run(() => post<Case>(`/cases/${c.id}/referral/info`, { answers }))}
        >
          Send answers
        </ButtonPrimary>
      </div>
    </section>
  );
}
