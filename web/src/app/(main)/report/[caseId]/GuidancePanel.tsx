// F-M1.7 First-aid guidance with voice (vetted library, F-M5.3) · F-M5.4 language selector.
"use client";

import { Square, Volume2 } from "lucide-react";
import { useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import Card from "@/app/components/Card";
import SourceBadge from "@/app/components/SourceBadge";
import AudioPlayer from "@/app/components/(voice)/AudioPlayer";
import type { Case } from "@/lib/api";
import { speak, stopSpeaking } from "@/lib/speech";
import { useGuidance, useMeta } from "@/lib/swr";

export default function ({
  c,
  role,
  language,
  onLanguage,
}: {
  c: Case;
  role: "reporter" | "clinician";
  language: string;
  onLanguage: (l: string) => void;
}) {
  const { data: meta } = useMeta();
  const condition = c.recommendation?.primary_condition_id ?? c.intake?.suspected_conditions[0]?.condition_id;
  const { data } = useGuidance(c.id, role, condition);
  const [playing, setPlaying] = useState(false);
  const langs = (meta?.languages ?? []) as { code: string; label: string; voice: boolean; note?: string }[];
  const lang = langs.find((l) => l.code === language);
  const voiceOk = lang?.voice !== false;

  const readAll = async () => {
    if (!data) return;
    setPlaying(true);
    for (const step of data.steps) {
      await speak(step.text, "guide", language);
    }
    setPlaying(false);
  };

  return (
    <Card
      title="What to do now"
      aside={
        <select
          value={language}
          onChange={(e) => onLanguage(e.target.value)}
          aria-label="Language"
          className="h-[2.5rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.5rem] text-[0.875rem]"
        >
          {langs.map((l) => (
            <option key={l.code} value={l.code}>
              {l.label}
            </option>
          ))}
        </select>
      }
    >
      {!voiceOk && <p className="mb-[.5rem] text-[0.875rem] text-warn-fg">{lang?.note ?? "Voice not yet available — text only"}</p>}
      {!data && <p className="text-muted">Guidance appears after the description is analysed.</p>}
      {data && (
        <>
          <ol className="flex flex-col gap-[.5rem]">
            {data.steps.map((s, i) => (
              <li key={s.id} className="flex items-start gap-[.5rem]">
                <span className="mt-[.625rem] w-[1.25rem] shrink-0 text-right font-bold text-brand tabular-nums">{i + 1}</span>
                <p className="flex-1 py-[.5rem] text-[1rem]">{s.text}</p>
                {voiceOk && <AudioPlayer text={s.text} language={language} label={undefined} aria-label={`Play step ${i + 1}`} />}
              </li>
            ))}
          </ol>
          <div className="mt-[.75rem] flex flex-wrap items-center gap-[.5rem]">
            {voiceOk &&
              (playing ? (
                <ButtonBase
                  onClick={() => {
                    stopSpeaking();
                    setPlaying(false);
                  }}
                >
                  <Square size={16} /> Stop
                </ButtonBase>
              ) : (
                <ButtonBase onClick={readAll}>
                  <Volume2 size={20} /> Read all
                </ButtonBase>
              ))}
            <SourceBadge kind={data.selected_by === "gemini" ? "gemini" : "template"} title="Steps come from a vetted library; AI only selects and orders" />
          </div>
          <p className="mt-[.75rem] rounded-[.5rem] bg-surface p-[.75rem] text-[0.875rem] font-medium">{data.disclaimer}</p>
        </>
      )}
    </Card>
  );
}
