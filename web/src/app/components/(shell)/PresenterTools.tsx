// Presenter tools: prepared cases, region pack, time, integration status, reset. Never part of the clinical UI.
"use client";

import { ArrowRight, Copy, Database, Loader2, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonGhost from "@/app/components/(buttons)/ButtonGhost";
import LiveDot from "@/app/components/(controls)/LiveDot";
import Segmented from "@/app/components/(controls)/Segmented";
import ModeIcon from "@/app/components/(transfer)/ModeIcon";
import { patch, post, type DemoCase, type SeedResponse, type Transfer } from "@/lib/api";
import { patientTitle } from "@/lib/clinical";
import { place } from "@/lib/format";
import { setPresenterOpen } from "@/lib/presenter";
import { useDemoCases, useMeta } from "@/lib/swr";
import { toast, toastError } from "@/lib/toast";

const SPEEDS = ["1", "10", "30", "60"] as const;

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="border-t-[1px] border-line py-[1.25rem] first:border-t-0 first:pt-[.5rem]">
      <h3 className="mb-[.75rem] text-[0.8125rem] font-[600] uppercase tracking-[0.06em] text-ink-3">{title}</h3>
      {children}
    </section>
  );
}

export default function ({ onDone }: { onDone?: () => void }) {
  const router = useRouter();
  const { data: meta } = useMeta();
  const { data: cases } = useDemoCases(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [line, setLine] = useState<string | null>(null);

  const run = async (key: string, fn: () => Promise<void>) => {
    setBusy(key);
    try {
      await fn();
      await mutate(() => true);
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(null);
    }
  };

  const start = (c: DemoCase) =>
    run(c.id, async () => {
      const t = await post<Transfer>(`/demo/cases/${c.id}`);
      setLine(c.suggested_note ?? null);
      router.push(`/crew/${t.id}`);
      if (!c.suggested_note) onDone?.();
    });

  if (!meta) return null;
  const services = [
    { name: "Presage", live: meta.adapters.presage === "live", text: meta.bridge.connected ? (meta.bridge.sdk === "ready" ? "Bridge connected" : meta.bridge.message ?? "Bridge connected, SDK not ready") : "Bridge not running · vitals simulated" },
    { name: "ElevenLabs", live: meta.adapters.elevenlabs === "real", text: meta.adapters.elevenlabs === "real" ? "Scribe + voice" : "Browser speech" },
    { name: "Gemini", live: meta.adapters.gemini === "real", text: meta.adapters.gemini === "real" ? "Live handoff drafting" : "Template drafting" },
    { name: "Database", live: meta.infra.database_kind !== "memory", text: meta.infra.database },
    { name: "Host", live: meta.infra.host_provider !== null && meta.infra.host_provider !== undefined, text: meta.infra.host },
  ];

  const seed = () =>
    run("seed", async () => {
      const res = await post<SeedResponse>("/insights/seed?days=60");
      toast(`Seeded ${res.inserted} transfers in ${(res.elapsed_ms / 1000).toFixed(1)} s`);
      setPresenterOpen(false);
      router.push("/insights");
    });

  return (
    <div>
      <Section title="Prepared cases">
        <ul className="flex flex-col gap-[.5rem]">
          {(cases ?? []).map((c) => {
            const region = meta.regions.find((r) => r.id === c.region_id);
            return (
              <li key={c.id}>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => start(c)}
                  className="group flex w-full items-center gap-[1rem] rounded-[.875rem] border-[1px] border-line p-[.875rem] text-left transition-colors hover:border-accent/40 hover:bg-accent-soft/40 disabled:opacity-60"
                >
                  <span className="flex h-[2.5rem] w-[2.5rem] shrink-0 items-center justify-center rounded-[.75rem] bg-well text-ink-2">
                    <ModeIcon mode={c.mode} size={18} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block font-[600]">{c.title}</span>
                    <span className="block truncate text-[0.8125rem] text-ink-2">
                      {patientTitle(c.patient)} · {place(region, c.origin_id)} → {place(region, c.destination_id)}
                    </span>
                  </span>
                  {busy === c.id ? <Loader2 size={18} className="animate-spin text-ink-3" /> : <ArrowRight size={18} className="text-ink-3 transition-transform group-hover:translate-x-[.125rem]" />}
                </button>
              </li>
            );
          })}
        </ul>
        {line && (
          <div className="rise-in mt-[.875rem] rounded-[.875rem] bg-accent-soft p-[.875rem]">
            <p className="text-[0.8125rem] font-[600] text-accent-strong">Suggested note to speak</p>
            <p className="mt-[.25rem] text-[0.9375rem]">“{line}”</p>
            <button
              type="button"
              className="mt-[.5rem] inline-flex items-center gap-[.375rem] text-[0.8125rem] font-[550] text-accent-strong"
              onClick={() => navigator.clipboard.writeText(line).then(() => toast("Copied"))}
            >
              <Copy size={14} /> Copy
            </button>
          </div>
        )}
      </Section>

      <Section title="Region">
        <Segmented
          label="Region"
          size="sm"
          value={meta.region.id}
          onChange={(v) => run(`region-${v}`, () => patch("/demo/state", { region_id: v }).then(() => undefined))}
          options={meta.regions.map((r) => ({ value: r.id, label: r.name }))}
        />
        <p className="mt-[.5rem] text-[0.8125rem] text-ink-3">Regions are data packs: hospitals, clinics and transport modes.</p>
      </Section>

      <Section title="Journey speed">
        <Segmented
          label="Journey speed"
          size="sm"
          value={String(meta.demo_state.speed_multiplier) as (typeof SPEEDS)[number]}
          onChange={(v) => run(`speed-${v}`, () => patch("/demo/state", { speed_multiplier: Number(v) }).then(() => undefined))}
          options={SPEEDS.map((s) => ({ value: s, label: `${s}×` }))}
        />
      </Section>

      <Section title="Services">
        <ul className="flex flex-col gap-[.625rem] text-[0.875rem]">
          {services.map((s) => (
            <li key={s.name} className="flex items-center gap-[.625rem]">
              <LiveDot tone={s.live ? "teal" : "idle"} />
              <span className="w-[5.5rem] shrink-0 font-[600]">{s.name}</span>
              <span className={twMerge("text-ink-2", !s.live && "text-ink-3")}>{s.text}</span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Network insights">
        <div className="flex flex-wrap items-center gap-[.5rem]">
          <ButtonGhost size="sm" disabled={busy !== null} onClick={seed}>
            {busy === "seed" ? <Loader2 size={15} className="animate-spin" /> : <Database size={15} />} Seed 60 days of history
          </ButtonGhost>
          <Link href="/insights" onClick={() => setPresenterOpen(false)} className="inline-flex items-center gap-[.375rem] text-[0.875rem] font-[550] text-accent-strong">
            Open insights <ArrowRight size={14} />
          </Link>
        </div>
        <p className="mt-[.5rem] text-[0.8125rem] text-ink-3">Synthetic, clearly flagged history in the transfer log. Re-seeding replaces it; live transfers are kept.</p>
      </Section>

      <Section title="Reset">
        <ButtonGhost
          size="sm"
          disabled={busy !== null}
          onClick={() =>
            window.confirm("Remove all transfers?") &&
            run("reset", async () => {
              await post("/demo/reset");
              setPresenterOpen(false);
              router.push("/crew");
            })
          }
          className="text-critical hover:text-critical"
        >
          <RotateCcw size={15} /> Clear all transfers
        </ButtonGhost>
      </Section>
    </div>
  );
}
