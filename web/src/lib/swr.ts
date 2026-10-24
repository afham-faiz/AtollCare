// Realtime = SWR polling every 2 s.
"use client";

import useSWR from "swr";

import { POLL_MS } from "@/app/config";
import {
  fetcher,
  type DemoCase,
  type InsightsResponse,
  type MetaResponse,
  type Transfer,
  type TransferListItem,
  type TrendResponse,
} from "@/lib/api";

const live = { refreshInterval: POLL_MS, keepPreviousData: true };

export const useMeta = () => useSWR<MetaResponse>("/meta", fetcher, { refreshInterval: 5000, keepPreviousData: true });
export const useTransfer = (id?: string) => useSWR<Transfer>(id ? `/transfers/${id}` : null, fetcher, live);
export const useTransfers = (status = "") =>
  useSWR<TransferListItem[]>(`/transfers${status ? `?status=${status}` : ""}`, fetcher, live);
export const useTrend = (id?: string) =>
  useSWR<TrendResponse>(id ? `/transfers/${id}/vitals/trend?window_min=90` : null, fetcher, { ...live, refreshInterval: 5000 });
export const useDemoCases = (enabled: boolean) => useSWR<DemoCase[]>(enabled ? "/demo/cases" : null, fetcher);
// network analytics change slowly; continuous aggregates refresh every few minutes
export const useInsights = (days: number) =>
  useSWR<InsightsResponse>(`/insights?days=${days}`, fetcher, { refreshInterval: 30000, keepPreviousData: true });
