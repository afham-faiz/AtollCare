// F-M7.5 Footer adapter pills ("Gemini: live", "Presage: mock").
"use client";

import { twMerge } from "tailwind-merge";

import { useMeta } from "@/lib/swr";

import PillBase from "./(pills)/PillBase";

const NAMES = { presage: "Presage", gemini: "Gemini", elevenlabs: "ElevenLabs", storage: "Storage" } as const;

export default function () {
  const { data, error } = useMeta();
  return (
    <footer className="mt-auto border-t-[1px] border-border px-[1rem] py-[1rem] text-[0.875rem] text-muted">
      <div className="mx-auto flex max-w-[90rem] flex-wrap items-center gap-[.5rem]">
        <span>Decision support only — every recommendation requires a clinician to act.</span>
        <span className="ml-auto flex flex-wrap gap-[.375rem]">
          {error && <PillBase className="border-alert text-alert">Engine: offline</PillBase>}
          {data &&
            (Object.keys(NAMES) as (keyof typeof NAMES)[]).map((k) => {
              const v = data.adapters[k];
              return (
                <PillBase key={k} className={twMerge("text-[0.875rem]", v === "real" && "border-brand text-brand")}>
                  {NAMES[k]}: {v === "real" ? "live" : v}
                </PillBase>
              );
            })}
        </span>
      </div>
    </footer>
  );
}
