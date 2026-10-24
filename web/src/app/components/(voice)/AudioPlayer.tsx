// F-M5.2 Play a sentence via ElevenLabs (or browser speech fallback).
"use client";

import { Loader2, Volume2 } from "lucide-react";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

import { speak } from "@/lib/speech";

export default function ({
  text,
  voice = "guide",
  language,
  label,
  className,
  ...props
}: Omit<React.JSX.IntrinsicElements["button"], "onClick"> & {
  text: string;
  voice?: "guide" | "status";
  language?: string;
  label?: string;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <button
      type="button"
      aria-label={label ?? "Play"}
      disabled={busy || !text}
      onClick={async () => {
        setBusy(true);
        try {
          await speak(text, voice, language);
        } finally {
          setBusy(false);
        }
      }}
      className={twMerge(
        "inline-flex min-h-[2.75rem] min-w-[2.75rem] items-center justify-center gap-[.375rem] rounded-[.5rem] text-brand hover:bg-brand-soft disabled:opacity-50",
        className,
      )}
      {...props}
    >
      {busy ? <Loader2 size={20} className="animate-spin" /> : <Volume2 size={20} />}
      {label && <span className="text-[0.875rem] font-medium">{label}</span>}
    </button>
  );
}
