// Review the handoff, then send it. On send the sheet condenses and travels to the transfer's status — the moment
// the case leaves the vehicle for the hospital.
"use client";

import { ArrowUpRight, Loader2 } from "lucide-react";
import { useRef, useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import Sheet from "@/app/components/(modals)/Sheet";
import SbarDocument from "@/app/components/(transfer)/SbarDocument";
import UrgencyBadge from "@/app/components/(transfer)/UrgencyBadge";
import { post, type Intervention, type Region, type Transfer } from "@/lib/api";
import { numeric, SOURCE_LABEL, type Source } from "@/lib/clinical";
import { place } from "@/lib/format";
import { toastError } from "@/lib/toast";

const KEY_VITALS = [
  ["heart_rate", "Heart rate", "bpm"],
  ["resp_rate", "Respiration", "/min"],
  ["spo2", "SpO₂", "%"],
  ["systolic_bp", "BP", "sys"],
  ["temperature_c", "Temp", "°C"],
] as const;

async function fly(from: HTMLElement, to: HTMLElement | null) {
  if (!to || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const a = from.getBoundingClientRect();
  const b = to.getBoundingClientRect();
  const dx = b.left + b.width / 2 - (a.left + a.width / 2);
  const dy = b.top + b.height / 2 - (a.top + a.height / 2);
  await from.animate(
    [
      { transform: "none", opacity: 1, filter: "none" },
      { transform: `translate(${dx * 0.08}px, ${dy * 0.08}px) scale(0.92)`, opacity: 1, offset: 0.3 },
      { transform: `translate(${dx}px, ${dy}px) scale(0.04)`, opacity: 0, filter: "blur(2px)" },
    ],
    { duration: 720, easing: "cubic-bezier(0.65, 0, 0.35, 1)", fill: "forwards" },
  ).finished;
}

export default function ({
  t,
  region,
  now,
  open,
  readOnly,
  onClose,
  onSent,
  onChanged,
}: {
  t: Transfer;
  region?: Region;
  now?: string;
  open: boolean;
  readOnly: boolean;
  onClose: () => void;
  onSent: (t: Transfer) => void;
  onChanged: (t: Transfer) => void;
}) {
  const panel = useRef<HTMLDivElement>(null);
  const [sending, setSending] = useState(false);
  const done = t.status === "arrived" || t.status === "closed";
  const remove = async (i: Intervention) => {
    try {
      onChanged(await post<Transfer>(`/transfers/${t.id}/interventions/remove`, { note_id: i.note_id, text: i.text }));
    } catch (err) {
      toastError(err);
    }
  };
  const dest = place(region, t.destination_id);
  const simulated = KEY_VITALS.filter(([k]) => t.latest[k]?.source === "simulated").map(([, label]) => label);

  const send = async () => {
    setSending(true);
    try {
      const next = await post<Transfer>(`/transfers/${t.id}/handoff`);
      if (panel.current) await fly(panel.current, document.getElementById("handoff-target"));
      onSent(next);
    } catch (err) {
      toastError(err);
    } finally {
      setSending(false);
    }
  };

  return (
    <Sheet
      open={open}
      onClose={onClose}
      panelRef={panel}
      title={readOnly ? `Handoff to ${dest}` : `Send handoff to ${dest}`}
      subtitle={readOnly ? "Updates live as you add notes and vitals" : "The receiving team sees this as soon as you send it"}
      footer={
        readOnly ? (
          <ButtonBase onClick={onClose}>Done</ButtonBase>
        ) : (
          <>
            <ButtonBase onClick={onClose} disabled={sending}>
              Not yet
            </ButtonBase>
            <ButtonPrimary onClick={send} disabled={sending}>
              {sending ? <Loader2 size={18} strokeWidth={1.75} className="animate-spin" /> : <ArrowUpRight size={18} strokeWidth={1.75} />}
              Send to {dest}
            </ButtonPrimary>
          </>
        )
      }
    >
      <div className="flex flex-col gap-[1.25rem]">
        <UrgencyBadge news2={t.news2} size="lg" className="self-start" />

        <dl className="grid grid-cols-3 gap-x-[1rem] gap-y-[.875rem] sm:grid-cols-5">
          {KEY_VITALS.map(([k, label, unit]) => {
            const lv = t.latest[k];
            const v = numeric(lv);
            return (
              <div key={k}>
                <dt className="text-[0.8125rem] text-ink-3">{label}</dt>
                <dd className="tnum text-[1.25rem] font-[500] tracking-[-0.02em]">
                  {v ?? "—"}
                  {v !== null && <span className="ml-[.125rem] text-[0.8125rem] font-[500] text-ink-3">{unit}</span>}
                </dd>
                <dd className="text-[0.75rem] text-ink-3">{lv ? SOURCE_LABEL[lv.source as Source] : "Not recorded"}</dd>
              </div>
            );
          })}
        </dl>
        {simulated.length > 0 && (
          <p className="rounded-[.75rem] border-[1px] border-dashed border-line-strong px-[.875rem] py-[.625rem] text-[0.875rem] text-ink-2">
            {simulated.join(" and ")} {simulated.length > 1 ? "are" : "is"} simulated, not measured. The hospital sees the same label.
          </p>
        )}

        <div className="border-t-[1px] border-line pt-[1.25rem]">
          <SbarDocument
            briefing={t.briefing}
            interventions={t.interventions}
            now={now}
            tz={region?.timezone}
            compact
            onRemove={done ? undefined : remove}
          />
        </div>
      </div>
    </Sheet>
  );
}
