// §10 Every AI output is badged; every assumption is labelled.
import { twMerge } from "tailwind-merge";

import PillBase from "./(pills)/PillBase";

const LABEL = {
  gemini: "AI-generated · Gemini",
  fallback: "Rule-based fallback",
  template: "Template",
  assumption: "DEMO ASSUMPTION",
  presage: "Source: Presage",
  mock: "Source: mock scan",
  manual: "Manual entry",
  elevenlabs: "Voice · ElevenLabs",
  browser: "Voice · browser",
} as const;

export default function ({
  kind,
  className,
  ...props
}: React.JSX.IntrinsicElements["span"] & { kind: keyof typeof LABEL }) {
  const tone =
    kind === "gemini" || kind === "presage" || kind === "elevenlabs"
      ? "border-brand bg-brand-soft text-brand"
      : kind === "assumption"
        ? "border-warn bg-warn-soft text-warn-fg"
        : "text-muted";
  return (
    <PillBase className={twMerge("text-[0.875rem]", tone, className)} {...props}>
      {LABEL[kind]}
    </PillBase>
  );
}
