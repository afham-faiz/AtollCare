// Crew home: packets a companion sent ahead from their phone. Starting a transfer from one carries all of it over —
// the account, the ID and the video's results — so nothing is asked twice.
"use client";

import { ArrowRight, ChevronDown, Loader2, Smartphone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import Segmented from "@/app/components/(controls)/Segmented";
import ModeIcon from "@/app/components/(transfer)/ModeIcon";
import { post, type Intake, type MetaResponse, type Transfer, type TransportMode } from "@/lib/api";
import { patientTitle } from "@/lib/clinical";
import { ago, MODE_LABEL, place } from "@/lib/format";
import { toastError } from "@/lib/toast";

import styles from "./Start.module.scss";

// what the packet holds, in a few words: the crew decides at a glance whether it's worth opening
function contents(i: Intake): { text: string; tone?: "warn" }[] {
  const out: { text: string; tone?: "warn" }[] = [];
  const scan = i.scans.at(-1);
  if (scan) {
    const v = scan.vitals;
    const seen = scan.signs?.findings.filter((f) => f.finding === "present").length ?? 0;
    if (scan.status === "processing") out.push({ text: "Video · analysing" });
    else
      out.push({
        text: ["Video", v?.heart_rate_bpm != null && `HR ${v.heart_rate_bpm}`, v?.respiration_rate_bpm != null && `RR ${v.respiration_rate_bpm}`, seen && `${seen} sign${seen > 1 ? "s" : ""} seen`]
          .filter(Boolean)
          .join(" · "),
      });
  }
  if (i.account) out.push({ text: i.account_source === "voice" ? "Spoken account" : "Written account" });
  if (i.identity) out.push(i.identity.needs_review ? { text: "ID · check by eye", tone: "warn" } : { text: "ID" });
  return out;
}

function Packet({ intake, meta }: { intake: Intake; meta: MetaResponse }) {
  const router = useRouter();
  const region = meta.regions.find((r) => r.id === intake.region_id);
  const hospitals = region?.facilities.filter((f) => f.kind === "hospital") ?? [];
  const [open, setOpen] = useState(false);
  const [origin, setOrigin] = useState("");
  const [dest, setDest] = useState("");
  const [mode, setMode] = useState<TransportMode | "">("");
  const [busy, setBusy] = useState(false);
  const chosenOrigin = intake.health_centre_id || origin || region?.facilities.find((f) => f.kind === "clinic")?.id || "";
  const chosenDest = dest || hospitals[0]?.id || "";
  const chosenMode = mode || region?.modes[0] || "";

  const start = async () => {
    setBusy(true);
    try {
      const t = await post<Transfer>(`/intakes/${intake.id}/transfer`, { origin_id: chosenOrigin, destination_id: chosenDest, mode: chosenMode });
      router.push(`/crew/${t.id}`);
    } catch (err) {
      toastError(err);
      setBusy(false);
    }
  };

  return (
    <li>
      <button type="button" className={twMerge(styles.row, "w-full text-left")} onClick={() => setOpen(!open)} aria-expanded={open}>
        <span className={twMerge(styles.rowIcon, styles.rowIconAccent)}>
          <Smartphone size={18} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-[.625rem]">
            <span className="font-[600]">{patientTitle(intake.patient)}</span>
            <span className="font-mono text-[0.8125rem] text-ink-3">{intake.code}</span>
            <span className="ml-auto shrink-0 text-[0.8125rem] text-ink-3">{intake.sent_at ? ago(intake.sent_at, meta.now) : ""}</span>
          </span>
          <span className="block truncate text-[0.875rem] text-ink-2">
            {intake.complaint ?? "No account"} · at {place(region, intake.health_centre_id)}
          </span>
          <span className={styles.chips}>
            {contents(intake).map((c) => (
              <span key={c.text} className={twMerge(styles.chip, c.tone === "warn" && styles.chipWarn)}>
                {c.text}
              </span>
            ))}
          </span>
        </span>
        <ChevronDown size={18} className={twMerge("shrink-0 text-ink-3 transition-transform", open && "rotate-180")} />
      </button>

      {open && (
        <div className={styles.packetForm}>
          {!intake.health_centre_id && (
            <label className={field.field}>
              <span className={field.label}>From</span>
              <select className={field.select} value={chosenOrigin} onChange={(e) => setOrigin(e.target.value)}>
                {region?.facilities.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.short_name}
                  </option>
                ))}
              </select>
            </label>
          )}
          <label className={field.field}>
            <span className={field.label}>To</span>
            <select className={field.select} value={chosenDest} onChange={(e) => setDest(e.target.value)}>
              {hospitals.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.short_name}
                </option>
              ))}
            </select>
          </label>
          <div className={field.field}>
            <span className={field.label}>Transport</span>
            <Segmented
              label="Transport"
              value={chosenMode || null}
              onChange={(m) => setMode(m)}
              className="w-full"
              options={(region?.modes ?? []).map((m) => ({ value: m, label: <><ModeIcon mode={m} /> {MODE_LABEL[m]}</> }))}
            />
          </div>
          <ButtonPrimary size="lg" className="w-full" onClick={start} disabled={busy || !chosenDest || !chosenMode || !chosenOrigin}>
            {busy && <Loader2 size={18} className="animate-spin" />} Start transfer <ArrowRight size={18} />
          </ButtonPrimary>
        </div>
      )}
    </li>
  );
}

export default function ({ intakes, meta }: { intakes: Intake[]; meta: MetaResponse }) {
  return (
    <section className="rise-in">
      <h2 className={styles.eyebrow}>Sent ahead from a phone</h2>
      <ul className={styles.list}>
        {intakes.map((i) => (
          <Packet key={i.id} intake={i} meta={meta} />
        ))}
      </ul>
    </section>
  );
}
