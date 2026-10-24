// F-M4.2 Dispatch (route defaults to chosen, alternatives selectable; assets auto-picked, overridable),
// F-M4.3 live map, F-M4.5 manual arrival, F-M4.8 crew audio brief.
"use client";

import { ArrowLeft, Flag, Radio, Truck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import CaseHeadline from "@/app/components/(case)/CaseHeadline";
import CaseTimeline from "@/app/components/(case)/CaseTimeline";
import FamilyStatus from "@/app/components/(case)/FamilyStatus";
import ModeIcon from "@/app/components/(case)/ModeIcon";
import { RouteLegs } from "@/app/components/(case)/RouteCard";
import AtollMapLazy from "@/app/components/(map)/AtollMapLazy";
import Card from "@/app/components/Card";
import PillSeverity from "@/app/components/(pills)/PillSeverity";
import PillStatus from "@/app/components/(pills)/PillStatus";
import Skeleton from "@/app/components/Skeleton";
import WeatherBanner from "@/app/components/WeatherBanner";
import { api, post, type Case } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";
import { facilityName, fmtMin, fmtTime, MODE_LABEL } from "@/lib/format";
import { playUrlOrSpeak } from "@/lib/speech";
import { useAssets, useCase, useMeta, useTrack } from "@/lib/swr";
import { toastError } from "@/lib/toast";
import { useEventToasts } from "@/lib/useEventToasts";

export default function ({ caseId }: { caseId: string }) {
  const { data: c } = useCase(caseId);
  const { data: meta } = useMeta();
  const { data: assets } = useAssets();
  const { data: track } = useTrack(caseId, !!c && c.transport.status !== "none");
  const { busy, run } = useCaseAction(caseId);
  const [routeId, setRouteId] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Record<number, string>>({});
  const [brief, setBrief] = useState<string | null>(null);
  useEventToasts(c);

  if (!c || !meta) return <Skeleton className="h-[20rem]" />;
  const rec = c.recommendation;
  const options = rec?.alternatives ?? [];
  const selectedId = routeId ?? rec?.chosen_route_id ?? null;
  const selected = c.transport.route ?? options.find((r) => r.id === selectedId) ?? null;
  const canDispatch = c.status === "accepted";

  const dispatch = () =>
    run(() =>
      post<Case>(`/cases/${c.id}/dispatch`, {
        route_id: selectedId,
        asset_ids: Object.values(overrides).filter(Boolean),
      }),
    );

  const playBrief = async () => {
    try {
      const res = await api<{ text: string; audio_url: string | null }>(`/cases/${c.id}/crew-brief?speak=true`);
      setBrief(res.text);
      await playUrlOrSpeak(res.audio_url, res.text);
    } catch (err) {
      toastError(err);
    }
  };

  return (
    <div className="flex flex-col gap-[1rem]">
      <Link href="/transport" className="inline-flex min-h-[2.75rem] items-center gap-[.25rem] text-[0.875rem] text-brand">
        <ArrowLeft size={16} /> Dispatch board
      </Link>
      <header className="flex flex-wrap items-center gap-[.75rem]">
        <h1 className="text-[1.75rem] font-bold tabular-nums">{c.short_code}</h1>
        <PillSeverity severity={rec?.severity} />
        <PillStatus status={c.status} />
        <span className="text-muted">
          {facilityName(meta.facilities, c.origin_facility_id)} → {facilityName(meta.facilities, c.referral?.destination_id ?? rec?.destination_id)}
        </span>
      </header>
      <CaseHeadline headline={c.headline} />
      <WeatherBanner meta={meta} />

      <div className="grid gap-[1rem] lg:grid-cols-[24rem_1fr]">
        <div className="flex min-w-0 flex-col gap-[1rem]">
          {canDispatch ? (
            <Card title="Dispatch">
              <fieldset className="flex flex-col gap-[.5rem]">
                <legend className="mb-[.5rem] text-[0.875rem] text-muted">Route</legend>
                {options.map((r) => (
                  <label
                    key={r.id}
                    className={twMerge(
                      "flex cursor-pointer gap-[.5rem] rounded-[.5rem] border-[1px] border-border p-[.75rem]",
                      selectedId === r.id && "border-brand bg-brand-soft",
                      !r.feasible && "opacity-60",
                    )}
                  >
                    <input type="radio" name="route" checked={selectedId === r.id} onChange={() => setRouteId(r.id)} disabled={!r.feasible} />
                    <span className="min-w-0 flex-1 text-[0.875rem]">
                      <span className="block font-medium">{r.label}</span>
                      <span className="block tabular-nums text-muted">
                        {fmtMin(r.total_min)} · ETA {fmtTime(r.arrive_at)}
                        {r.id === rec?.chosen_route_id && " · recommended"}
                      </span>
                      {!r.feasible && <span className="block text-alert">{r.infeasible_reasons.join("; ")}</span>}
                    </span>
                  </label>
                ))}
              </fieldset>
              {selected && (
                <div className="mt-[1rem] flex flex-col gap-[.5rem]">
                  <p className="text-[0.875rem] text-muted">Assets (auto-picked nearest available — override if needed)</p>
                  {selected.legs.map((leg, i) =>
                    leg.asset_id ? (
                      <label key={i} className="flex items-center gap-[.5rem] text-[0.875rem]">
                        <ModeIcon mode={leg.mode} className="text-brand" />
                        <span className="w-[7rem] shrink-0">{MODE_LABEL[leg.mode]}</span>
                        <select
                          value={overrides[i] ?? leg.asset_id}
                          onChange={(e) => setOverrides((o) => ({ ...o, [i]: e.target.value }))}
                          className="h-[2.5rem] min-w-0 flex-1 rounded-[.5rem] border-[1px] border-border bg-raised px-[.375rem]"
                        >
                          {(assets ?? [])
                            .filter((a) => a.mode === leg.mode && (a.status === "available" || a.id === leg.asset_id))
                            .map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.id} · {facilityName(meta.facilities, a.home_facility_id)}
                              </option>
                            ))}
                        </select>
                      </label>
                    ) : null,
                  )}
                </div>
              )}
              <ButtonPrimary className="mt-[1rem] w-full" disabled={busy || !selected?.feasible} onClick={dispatch}>
                <Truck size={20} /> {busy ? "Dispatching…" : "Dispatch"}
              </ButtonPrimary>
            </Card>
          ) : (
            <Card title={c.transport.status === "none" ? "Not ready" : "Transfer"}>
              {c.transport.status === "none" ? (
                <p className="text-muted">Dispatch becomes available once the destination hospital accepts the referral.</p>
              ) : (
                selected && <RouteLegs route={selected} facilities={meta.facilities} />
              )}
              {c.transport.eta && c.transport.status !== "arrived" && (
                <p className="mt-[.75rem] text-[1.5rem] font-bold tabular-nums">ETA {fmtTime(c.transport.eta)}</p>
              )}
              <div className="mt-[.75rem] flex flex-wrap gap-[.5rem]">
                {["dispatched", "in_transit"].includes(c.status) && (
                  <ButtonBase disabled={busy} onClick={() => run(() => post<Case>(`/cases/${c.id}/arrive`))}>
                    <Flag size={20} /> Mark arrived
                  </ButtonBase>
                )}
              </div>
            </Card>
          )}
          <Card title="Crew brief">
            <ButtonBase onClick={playBrief}>
              <Radio size={20} /> Play crew brief
            </ButtonBase>
            {brief && <p className="mt-[.75rem] text-[0.875rem]">{brief}</p>}
          </Card>
          {c.status !== "draft" && <FamilyStatus c={c} now={meta.now} showShare={false} />}
        </div>
        <div className="flex min-w-0 flex-col gap-[1rem]">
          <AtollMapLazy
            facilities={meta.facilities}
            height="32rem"
            cases={[
              {
                id: c.id,
                label: c.short_code,
                originId: c.origin_facility_id,
                destinationId: c.referral?.destination_id ?? rec?.destination_id,
                route: selected,
                track,
                highlight: true,
              },
            ]}
          />
          <CaseTimeline events={c.timeline} now={meta.now} />
        </div>
      </div>
    </div>
  );
}
