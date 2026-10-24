"use client";

import { X } from "lucide-react";
import { twMerge } from "tailwind-merge";

import { dismiss, useToasts } from "@/lib/toast";

const TONE = {
  info: "border-l-brand",
  warn: "border-l-warn",
  error: "border-l-alert",
};

export default function () {
  const toasts = useToasts();
  return (
    <div className="fixed bottom-[1rem] right-[1rem] left-[1rem] z-[3000] flex flex-col items-end gap-[.5rem] pointer-events-none">
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={twMerge(
            "pointer-events-auto flex max-w-[28rem] items-start gap-[.75rem] rounded-[.5rem] border-l-[.25rem] border-[1px] border-border bg-surface px-[1rem] py-[.75rem] shadow-lg",
            TONE[t.tone],
          )}
        >
          <p className="text-[0.875rem]">{t.text}</p>
          <button type="button" aria-label="Dismiss" onClick={() => dismiss(t.id)} className="text-muted">
            <X size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}
