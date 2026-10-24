// F-M1.4 Vitals capture: Camera scan (Presage) | Enter manually; NEWS2 card updates live.
"use client";

import { useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import News2Card from "@/app/components/(case)/News2Card";
import Card from "@/app/components/Card";
import CameraScan from "@/app/components/(vitals)/CameraScan";
import ManualVitalsForm from "@/app/components/(vitals)/ManualVitalsForm";
import type { Case } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";
import { sendVitals } from "@/lib/offline";

export default function ({
  c,
  scanEnabled,
  speed,
  clinician,
}: {
  c: Case;
  scanEnabled: boolean;
  speed: number;
  clinician: boolean;
}) {
  const [tab, setTab] = useState<"scan" | "manual">(scanEnabled ? "scan" : "manual");
  const { busy, run } = useCaseAction(c.id);

  const tabs = [
    { id: "scan", label: "Camera scan", disabled: !scanEnabled },
    { id: "manual", label: "Enter manually", disabled: false },
  ] as const;

  return (
    <div className="grid gap-[1rem] lg:grid-cols-[1fr_20rem]">
      <Card title="2 · Vitals">
        <div role="tablist" className="mb-[1rem] flex gap-[.25rem] rounded-[.5rem] bg-surface p-[.25rem]">
          {tabs.map((t) => (
            <button
              key={t.id}
              role="tab"
              type="button"
              aria-selected={tab === t.id}
              disabled={t.disabled}
              onClick={() => setTab(t.id)}
              className={twMerge(
                "min-h-[2.75rem] flex-1 rounded-[.375rem] font-medium text-muted disabled:opacity-40",
                tab === t.id && "bg-raised text-fg shadow-sm",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
        {!scanEnabled && <p className="mb-[.75rem] text-[0.875rem] text-muted">Camera scan disabled on this server (manual mode).</p>}
        {tab === "scan" && scanEnabled ? (
          <CameraScan
            caseId={c.id}
            speedMultiplier={speed}
            onFallback={() => setTab("manual")}
            onReading={() => mutate(`/cases/${c.id}`)}
          />
        ) : (
          <ManualVitalsForm
            busy={busy}
            onSubmit={async (req) => {
              await run(() => sendVitals(c.id, req));
            }}
          />
        )}
      </Card>
      <News2Card news2={c.news2} showPrompt={clinician} />
    </div>
  );
}
