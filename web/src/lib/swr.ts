// Realtime = SWR polling every 2 s (§5, no websockets).
"use client";

import useSWR from "swr";

import { POLL_MS } from "@/app/config";
import {
  fetcher,
  type Case,
  type CaseListItem,
  type DemoState,
  type GuidanceResponse,
  type HospitalCapacity,
  type MetaResponse,
  type RouteOption,
  type TrackResponse,
  type TransportAsset,
  type TrendResponse,
} from "@/lib/api";

const live = { refreshInterval: POLL_MS, revalidateOnFocus: true, keepPreviousData: true };

export const useMeta = () => useSWR<MetaResponse>("/meta", fetcher, { refreshInterval: 5000, keepPreviousData: true });
export const useCase = (id?: string) => useSWR<Case>(id ? `/cases/${id}` : null, fetcher, live);
export const useCases = (query = "") => useSWR<CaseListItem[]>(`/cases${query}`, fetcher, live);
export const useTrend = (id?: string, windowMin = 60) =>
  useSWR<TrendResponse>(id ? `/cases/${id}/vitals/trend?window_min=${windowMin}` : null, fetcher, live);
export const useTrack = (id?: string, active = true) =>
  useSWR<TrackResponse>(id && active ? `/cases/${id}/track` : null, fetcher, live);
export const useRoutes = (id?: string, enabled = true) =>
  useSWR<RouteOption[]>(id && enabled ? `/cases/${id}/routes` : null, fetcher, { refreshInterval: 10000 });
export const useCapacity = () => useSWR<HospitalCapacity[]>("/hospitals/capacity", fetcher, live);
export const useAssets = () => useSWR<TransportAsset[]>("/transport/assets", fetcher, live);
export const useDemoState = () => useSWR<DemoState>("/demo/state", fetcher, live);
export const useGuidance = (id?: string, role = "reporter", condition?: string | null) =>
  useSWR<GuidanceResponse>(id ? [`/cases/${id}/guidance?role=${role}`, condition] : null, ([path]: [string]) =>
    fetcher<GuidanceResponse>(path),
  );
