// F-M4.1 Dispatch board (Ready / In transit / Arrived today) + F-M4.3 live map of all active transfers.
"use client";

import Link from "next/link";
import useSWR from "swr";

import { RouteLegs } from "@/app/components/(case)/RouteCard";
import AtollMapLazy from "@/app/components/(map)/AtollMapLazy";
import type { MapCase } from "@/app/components/(map)/AtollMap";
import Card from "@/app/components/Card";
import PillSeverity from "@/app/components/(pills)/PillSeverity";
import PillStatus from "@/app/components/(pills)/PillStatus";
import Skeleton from "@/app/components/Skeleton";
import WeatherBanner from "@/app/components/WeatherBanner";
import { POLL_MS } from "@/app/config";
import { fetcher, type Case, type CaseListItem, type Facility, type TrackResponse } from "@/lib/api";
import { facilityName, fmtMin, fmtTime } from "@/lib/format";
import { useCases, useMeta } from "@/lib/swr";

import AssetRoster from "./AssetRoster";

const COLUMNS = [
  { id: "ready", title: "Ready to dispatch", statuses: ["accepted"] },
  { id: "transit", title: "In transit", statuses: ["dispatched", "in_transit"] },
  { id: "arrived", title: "Arrived today", statuses: ["arrived", "closed"] },
];

type Detail = { c: Case; track: TrackResponse | null };

async function loadDetails(ids: string[]): Promise<Record<string, Detail>> {
  const rows = await Promise.all(
    ids.map(async (id) => {
      const c = await fetcher<Case>(`/cases/${id}`);
      const track = c.transport.status !== "none" ? await fetcher<TrackResponse>(`/cases/${id}/track`) : null;
      return [id, { c, track }] as const;
    }),
  );
  return Object.fromEntries(rows);
}

function BoardCard({ item, detail, facilities }: { item: CaseListItem; detail?: Detail; facilities: Facility[] }) {
  const c = detail?.c;
  const route = c?.transport.route ?? c?.recommendation?.alternatives.find((r) => r.id === c.recommendation?.chosen_route_id);
  const assets = route?.legs.map((l) => l.asset_id).filter(Boolean) ?? [];
  return (
    <Link href={`/transport/${item.id}`} className="block rounded-[.75rem] border-[1px] border-border bg-raised p-[.75rem] hover:border-brand">
      <div className="mb-[.5rem] flex flex-wrap items-center gap-[.5rem]">
        <span className="font-bold tabular-nums">{item.short_code}</span>
        <PillSeverity severity={item.severity} />
        <PillStatus status={item.status} />
      </div>
      <p className="mb-[.5rem] text-[0.875rem] text-muted">
        {facilityName(facilities, item.origin_facility_id)} → {facilityName(facilities, item.destination_id)}
      </p>
      {route ? <RouteLegs route={route} facilities={facilities} /> : <Skeleton className="h-[3rem]" />}
      <p className="mt-[.5rem] text-[0.875rem] tabular-nums">
        ETA {fmtTime(item.eta)}
        {route?.window_margin_min !== null && route?.window_margin_min !== undefined && (
          <span className={route.window_margin_min < 0 ? "text-alert" : "text-brand"}>
            {" "}· {route.window_margin_min < 0 ? `${fmtMin(-route.window_margin_min)} over window` : `${fmtMin(route.window_margin_min)} margin`}
          </span>
        )}
      </p>
      {assets.length > 0 && <p className="text-[0.875rem] text-muted">Assets: {assets.join(", ")}</p>}
    </Link>
  );
}

export default function () {
  const { data: meta } = useMeta();
  const { data: cases } = useCases("?status=accepted,dispatched,in_transit,arrived,closed");
  const ids = (cases ?? []).map((c) => c.id);
  const { data: details } = useSWR(ids.length ? ["board", ...ids] : null, ([, ...rest]: string[]) => loadDetails(rest), {
    refreshInterval: POLL_MS,
    keepPreviousData: true,
  });

  if (!meta) return <Skeleton className="h-[20rem]" />;

  const mapCases: MapCase[] = (cases ?? [])
    .filter((c) => ["accepted", "dispatched", "in_transit"].includes(c.status))
    .map((c) => {
      const d = details?.[c.id];
      return {
        id: c.id,
        label: c.short_code,
        originId: c.origin_facility_id,
        destinationId: c.destination_id,
        route: d?.c.transport.route ?? d?.c.recommendation?.alternatives.find((r) => r.id === d.c.recommendation?.chosen_route_id),
        track: d?.track,
        highlight: c.status !== "accepted",
      };
    });

  return (
    <div className="flex flex-col gap-[1rem]">
      <h1 className="text-[1.5rem] font-bold">Transport coordination</h1>
      <WeatherBanner meta={meta} />
      <div className="grid gap-[1rem] lg:grid-cols-[1fr_22rem]">
        <div className="flex min-w-0 flex-col gap-[1rem]">
          <div className="grid gap-[1rem] md:grid-cols-2 2xl:grid-cols-3">
            {COLUMNS.map((col) => {
              const items = (cases ?? []).filter((c) => col.statuses.includes(c.status));
              return (
                <Card key={col.id} title={`${col.title} (${items.length})`} className="bg-surface">
                  <div className="flex flex-col gap-[.5rem]">
                    {!cases && <Skeleton className="h-[6rem]" />}
                    {cases && items.length === 0 && <p className="text-[0.875rem] text-muted">None</p>}
                    {items.map((item) => (
                      <BoardCard key={item.id} item={item} detail={details?.[item.id]} facilities={meta.facilities} />
                    ))}
                  </div>
                </Card>
              );
            })}
          </div>
          <AtollMapLazy facilities={meta.facilities} cases={mapCases} height="28rem" fit={mapCases.length > 0} />
        </div>
        <AssetRoster facilities={meta.facilities} />
      </div>
    </div>
  );
}
