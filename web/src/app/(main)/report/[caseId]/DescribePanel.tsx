// F-M1.2 Describe what's happening (text or voice) → Gemini intake; quick answers to missing_info re-run intake.
"use client";

import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import IntakeChips from "@/app/components/(case)/IntakeChips";
import Card from "@/app/components/Card";
import VoiceRecorder from "@/app/components/(voice)/VoiceRecorder";
import { post, type Case } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";
import { loadDraftText, saveDraftText } from "@/lib/offline";

import styles from "../Report.module.scss";

export default function ({ c, language }: { c: Case; language: string }) {
  const [text, setText] = useState("");
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const { busy, run } = useCaseAction(c.id);

  useEffect(() => {
    setText(c.intake?.raw_text || loadDraftText(c.id));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [c.id]);

  const update = (t: string) => {
    setText(t);
    saveDraftText(c.id, t);
  };

  const analyse = (raw: string) =>
    run(async () => {
      const res = await post<Case>(`/cases/${c.id}/intake`, { raw_text: raw, language });
      saveDraftText(c.id, "");
      return res;
    });

  const submitAnswers = () => {
    const extra = Object.entries(answers)
      .filter(([, a]) => a.trim())
      .map(([q, a]) => `${q} ${a.trim()}`)
      .join(". ");
    if (!extra) return;
    const raw = `${text.trim()}${text.trim().endsWith(".") ? "" : "."} ${extra}.`;
    update(raw);
    setAnswers({});
    analyse(raw);
  };

  return (
    <div className="flex flex-col gap-[1rem]">
      <Card title="1 · What's happening?">
        <label className={styles.field}>
          <span>Describe symptoms, when they started, anything that changed</span>
          <textarea value={text} onChange={(e) => update(e.target.value)} placeholder="e.g. Crushing chest pain for 40 minutes, sweating…" />
        </label>
        <div className="mt-[.75rem] flex flex-wrap gap-[.5rem]">
          <VoiceRecorder caseId={c.id} language={language} onText={(t) => update(text ? `${text} ${t}` : t)} />
          <ButtonPrimary onClick={() => analyse(text)} disabled={busy || !text.trim()}>
            <Sparkles size={20} /> {busy ? "Analysing…" : "Analyse"}
          </ButtonPrimary>
        </div>
      </Card>
      {c.intake && (
        <IntakeChips intake={c.intake}>
          {c.intake.missing_info.length > 0 && (
            <div className="mt-[1rem] flex flex-col gap-[.5rem]">
              <p className="text-[0.875rem] font-semibold">Questions to answer</p>
              {c.intake.missing_info.map((q) => (
                <label key={q} className={styles.field}>
                  <span>{q}</span>
                  <input value={answers[q] ?? ""} onChange={(e) => setAnswers((a) => ({ ...a, [q]: e.target.value }))} />
                </label>
              ))}
              <ButtonPrimary onClick={submitAnswers} disabled={busy || !Object.values(answers).some((a) => a.trim())}>
                Add answers & re-analyse
              </ButtonPrimary>
            </div>
          )}
        </IntakeChips>
      )}
    </div>
  );
}
