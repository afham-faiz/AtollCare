"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { twMerge } from "tailwind-merge";

import { dismiss, useToasts } from "@/lib/toast";

const TONE = {
  info: { icon: CheckCircle2, cls: "text-sage" },
  warn: { icon: Info, cls: "text-caution" },
  error: { icon: AlertCircle, cls: "text-critical" },
};

export default function () {
  const toasts = useToasts();
  return (
    <div className="pointer-events-none fixed top-[4.5rem] left-1/2 z-[3000] flex w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2 flex-col gap-[.5rem]" aria-live="polite">
      {toasts.map((t) => {
        const { icon: Icon, cls } = TONE[t.tone];
        return (
          <div
            key={t.id}
            role="status"
            className="glass rise-in pointer-events-auto flex items-center gap-[.75rem] rounded-full py-[.625rem] pl-[1rem] pr-[.75rem]"
          >
            <Icon size={18} strokeWidth={1.75} className={twMerge("shrink-0", cls)} />
            <p className="flex-1 text-[0.9375rem]">{t.text}</p>
            <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)} className="grid h-[2rem] w-[2rem] shrink-0 place-items-center rounded-full text-ink-3 hover:bg-well hover:text-ink">
              <X size={16} strokeWidth={1.75} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
