"use client";

import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { twMerge } from "tailwind-merge";

import { dismiss, useToasts } from "@/lib/toast";

const TONE = {
  info: { icon: CheckCircle2, cls: "text-teal" },
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
            className="rise-in pointer-events-auto flex items-start gap-[.75rem] rounded-[1rem] border-[1px] border-line bg-surface px-[1rem] py-[.75rem] shadow-3"
          >
            <Icon size={18} className={twMerge("mt-[.125rem] shrink-0", cls)} />
            <p className="flex-1 text-[0.9375rem]">{t.text}</p>
            <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)} className="text-ink-3 hover:text-ink">
              <X size={16} />
            </button>
          </div>
        );
      })}
    </div>
  );
}
