import { Sparkles } from "lucide-react";
import { twMerge } from "tailwind-merge";

import PillBase from "@/app/components/(pills)/PillBase";

export default function ({ ai, className }: { ai: boolean; className?: string }) {
  return (
    <PillBase className={twMerge(ai ? "border-brand/30 bg-brand-soft text-brand-strong" : "text-muted", className)}>
      {ai && <Sparkles size={14} />}
      {ai ? "Gemini" : "Template"}
    </PillBase>
  );
}
