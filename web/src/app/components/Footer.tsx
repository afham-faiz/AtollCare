// Footer: safety line, live/simulated status of each integration, link to demo controls.
"use client";

import Link from "next/link";
import { twMerge } from "tailwind-merge";

import { useMeta } from "@/lib/swr";

export default function () {
  const { data: meta, error } = useMeta();
  const items = meta
    ? [
        { label: "Presage", on: meta.adapters.presage === "live", text: meta.adapters.presage === "live" ? "live" : "simulated" },
        { label: "ElevenLabs", on: meta.adapters.elevenlabs === "real", text: meta.adapters.elevenlabs === "real" ? "live" : "browser voice" },
        { label: "Gemini", on: meta.adapters.gemini === "real", text: meta.adapters.gemini === "real" ? "live" : "templates" },
      ]
    : [];
  return (
    <footer className="mt-auto border-t-[1px] border-border bg-surface px-[1rem] py-[.75rem] text-[0.875rem] text-muted">
      <div className="mx-auto flex max-w-[90rem] flex-wrap items-center gap-x-[1.25rem] gap-y-[.5rem]">
        <span>Decision support only — clinicians decide.</span>
        {error && <span className="text-alert">Server offline</span>}
        {items.map((i) => (
          <span key={i.label} className="flex items-center gap-[.375rem]">
            <span className={twMerge("h-[.5rem] w-[.5rem] rounded-[50%] bg-faint", i.on && "bg-brand")} />
            {i.label}: {i.text}
          </span>
        ))}
        <Link href="/demo" className="ml-auto hover:text-fg">
          Demo controls
        </Link>
      </div>
    </footer>
  );
}
