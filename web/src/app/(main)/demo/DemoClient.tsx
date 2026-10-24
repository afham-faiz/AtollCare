// F-M8.1 Reset · F-M8.3 Scenarios (+Autoplay) · F-M8.4 presenter split view · F-M2.10 engine details.
"use client";

import { Play, RotateCcw, Star } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { mutate } from "swr";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonDanger from "@/app/components/(buttons)/ButtonDanger";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import CaseHeadline from "@/app/components/(case)/CaseHeadline";
import EngineInspector from "@/app/components/(case)/EngineInspector";
import Card from "@/app/components/Card";
import PillSeverity from "@/app/components/(pills)/PillSeverity";
import PillStatus from "@/app/components/(pills)/PillStatus";
import Skeleton from "@/app/components/Skeleton";
import WeatherBanner from "@/app/components/WeatherBanner";
import { post, type Case } from "@/lib/api";
import { facilityName } from "@/lib/format";
import { useCase, useCases, useMeta } from "@/lib/swr";
import { toast, toastError } from "@/lib/toast";

import PresenterView from "./PresenterView";
import WorldControls from "./WorldControls";

type Scenario = { id: string; title: string; story: string; proves: string; clock: string; presenter_notes?: string; hero?: boolean };

export default function ({ split }: { split: boolean }) {
  const { data: meta } = useMeta();
  const { data: cases } = useCases();
  const [autoplay, setAutoplay] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const latest = [...(cases ?? [])].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const { data: latestCase } = useCase(latest?.id);

  if (!meta) return <Skeleton className="h-[20rem]" />;
  if (split) return <PresenterView meta={meta} caseId={latest?.id} />;

  const refresh = () => Promise.all([mutate("/meta"), mutate((k) => typeof k === "string" && k.startsWith("/cases"))]);

  const load = async (id: string) => {
    setBusy(id);
    try {
      const c = await post<Case>(`/demo/scenario/${id}?autoplay=${autoplay}`);
      toast(`Loaded ${c.short_code} — ${id}`);
      await refresh();
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(null);
    }
  };

  const reset = async () => {
    if (!window.confirm("Delete all demo cases and reseed assets & capacity?")) return;
    setBusy("reset");
    try {
      await post("/demo/reset");
      await refresh();
      await mutate("/transport/assets");
      await mutate("/hospitals/capacity");
      toast("Demo reset");
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(null);
    }
  };

  const scenarios = meta.scenarios as Scenario[];

  return (
    <div className="flex flex-col gap-[1rem]">
      <div className="flex flex-wrap items-center gap-[.75rem]">
        <h1 className="text-[1.5rem] font-bold">Demo control</h1>
        <Link href="/demo?view=split" className="ml-auto">
          <ButtonBase tabIndex={-1}>Presenter view</ButtonBase>
        </Link>
        <ButtonDanger onClick={reset} disabled={busy !== null}>
          <RotateCcw size={20} /> Reset
        </ButtonDanger>
      </div>
      <WeatherBanner meta={meta} />
      <div className="grid gap-[1rem] lg:grid-cols-[1fr_24rem]">
        <div className="flex min-w-0 flex-col gap-[1rem]">
          <Card
            title="Scenarios"
            aside={
              <label className="flex min-h-[2.75rem] items-center gap-[.5rem] text-[0.875rem]">
                <input type="checkbox" checked={autoplay} onChange={(e) => setAutoplay(e.target.checked)} className="h-[1.25rem] w-[1.25rem]" />
                Autoplay (auto-refer → accept → dispatch)
              </label>
            }
          >
            <ul className="flex flex-col gap-[.75rem]">
              {scenarios.map((s) => (
                <li key={s.id} className="rounded-[.75rem] border-[1px] border-border p-[1rem]">
                  <div className="flex flex-wrap items-center gap-[.5rem]">
                    {s.hero && <Star size={16} className="text-warn" aria-label="Hero scenario" />}
                    <h3 className="font-semibold">{s.title}</h3>
                    <span className="text-[0.875rem] text-muted tabular-nums">{s.clock}</span>
                    <ButtonPrimary className="ml-auto" onClick={() => load(s.id)} disabled={busy !== null}>
                      <Play size={16} /> {busy === s.id ? "Loading…" : "Load"}
                    </ButtonPrimary>
                  </div>
                  <p className="mt-[.5rem] text-[0.9375rem]">{s.story}</p>
                  <p className="mt-[.25rem] text-[0.875rem] text-muted">Proves: {s.proves}</p>
                  {s.presenter_notes && <p className="mt-[.25rem] text-[0.875rem] text-brand">Presenter: {s.presenter_notes}</p>}
                </li>
              ))}
            </ul>
          </Card>
          <Card title="Cases">
            {(cases ?? []).length === 0 && <p className="text-muted">No cases yet.</p>}
            <ul className="flex flex-col">
              {(cases ?? []).map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-[.5rem] border-b-[1px] border-border py-[.5rem] text-[0.875rem]">
                  <span className="font-bold tabular-nums">{c.short_code}</span>
                  <PillSeverity severity={c.severity} />
                  <PillStatus status={c.status} />
                  <span className="text-muted">
                    {facilityName(meta.facilities, c.origin_facility_id)} → {facilityName(meta.facilities, c.destination_id)}
                  </span>
                  <span className="ml-auto flex gap-[.75rem]">
                    <Link className="text-brand underline" href={`/report/${c.id}`}>report</Link>
                    <Link className="text-brand underline" href={`/hospital/${c.id}`}>hospital</Link>
                    <Link className="text-brand underline" href={`/transport/${c.id}`}>transport</Link>
                    <Link className="text-brand underline" href={`/case/${c.id}`}>family</Link>
                  </span>
                </li>
              ))}
            </ul>
          </Card>
          {latestCase && (
            <>
              <CaseHeadline headline={latestCase.headline} />
              <EngineInspector c={latestCase} facilities={meta.facilities} />
            </>
          )}
        </div>
        <WorldControls meta={meta} />
      </div>
    </div>
  );
}
