// Demo controls (stage only): region pack, sim speed, example patient, reset, integration status.
"use client";

import { Loader2, RotateCcw, UserPlus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonDanger from "@/app/components/(buttons)/ButtonDanger";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import Card from "@/app/components/Card";
import Skeleton from "@/app/components/Skeleton";
import { patch, post, type Transfer } from "@/lib/api";
import { ago } from "@/lib/format";
import { useMeta } from "@/lib/swr";
import { toast, toastError } from "@/lib/toast";

const SPEEDS = [1, 10, 30, 60];

export default function () {
  const router = useRouter();
  const { data: meta } = useMeta();
  const [busy, setBusy] = useState<string | null>(null);
  if (!meta) return <Skeleton className="h-[20rem]" />;

  const run = async (key: string, fn: () => Promise<unknown>) => {
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

  const status = [
    {
      name: "Presage",
      ok: meta.adapters.presage === "live",
      text: meta.bridge.connected
        ? meta.bridge.sdk === "ready"
          ? `Bridge connected · SmartSpectra ${meta.bridge.version ?? ""}`
          : `Bridge connected · ${meta.bridge.message ?? meta.bridge.sdk}`
        : "Bridge not running → simulated vitals",
    },
    { name: "ElevenLabs", ok: meta.adapters.elevenlabs === "real", text: meta.adapters.elevenlabs === "real" ? "Scribe + TTS live" : "No key → browser speech" },
    { name: "Gemini", ok: meta.adapters.gemini === "real", text: meta.adapters.gemini === "real" ? "Live briefings" : "No key → template briefings" },
    { name: "Storage", ok: meta.adapters.storage === "real", text: meta.adapters.storage === "real" ? "Vultr Object Storage" : "Local disk" },
  ];

  return (
    <div className="mx-auto grid max-w-[64rem] gap-[1rem] md:grid-cols-2">
      <Card title="Region pack">
        <div className="flex flex-col gap-[.5rem]">
          {meta.regions.map((r) => (
            <button
              key={r.id}
              type="button"
              onClick={() => run(`region-${r.id}`, () => patch("/demo/state", { region_id: r.id }))}
              className={twMerge(
                "rounded-[.625rem] border-[1px] border-border p-[.875rem] text-left hover:border-brand",
                meta.region.id === r.id && "border-brand bg-brand-soft",
              )}
            >
              <strong>{r.name}</strong>
              <p className="text-[0.875rem] text-muted">{r.description}</p>
            </button>
          ))}
        </div>
      </Card>

      <div className="flex flex-col gap-[1rem]">
        <Card title="Example patient">
          <p className="mb-[.75rem] text-[0.9375rem] text-muted">Starts the {meta.region.name} example with 8 minutes of history.</p>
          <ButtonPrimary
            className="w-full"
            disabled={busy !== null}
            onClick={() =>
              run("example", async () => {
                const t = await post<Transfer>("/demo/example");
                toast(`Started ${t.code}`);
                router.push(`/crew/${t.id}`);
              })
            }
          >
            {busy === "example" ? <Loader2 size={18} className="animate-spin" /> : <UserPlus size={18} />} Start example transfer
          </ButtonPrimary>
        </Card>

        <Card title="Time">
          <p className="mb-[.75rem] text-[0.9375rem] text-muted">Speeds up the journey (ETA, position, simulated vitals).</p>
          <div className="flex gap-[.5rem]">
            {SPEEDS.map((s) => (
              <ButtonBase
                key={s}
                className={twMerge("flex-1", meta.demo_state.speed_multiplier === s && "border-brand bg-brand-soft text-brand-strong")}
                onClick={() => run(`speed-${s}`, () => patch("/demo/state", { speed_multiplier: s }))}
              >
                {s}×
              </ButtonBase>
            ))}
          </div>
        </Card>

        <Card title="Integrations">
          <ul className="flex flex-col gap-[.5rem] text-[0.9375rem]">
            {status.map((s) => (
              <li key={s.name} className="flex items-center gap-[.5rem]">
                <span className={twMerge("h-[.5rem] w-[.5rem] shrink-0 rounded-[50%] bg-warn", s.ok && "bg-brand")} />
                <strong className="w-[6rem] shrink-0">{s.name}</strong>
                <span className="text-muted">{s.text}</span>
              </li>
            ))}
          </ul>
          {meta.bridge.last_seen && <p className="mt-[.5rem] text-[0.875rem] text-faint">Bridge last seen {ago(meta.bridge.last_seen)}</p>}
        </Card>

        <ButtonDanger
          disabled={busy !== null}
          onClick={() => window.confirm("Delete all transfers?") && run("reset", () => post("/demo/reset"))}
        >
          <RotateCcw size={18} /> Reset demo
        </ButtonDanger>
      </div>
    </div>
  );
}
