// F-M1.10 Offline-tolerant draft: unsent text and vitals kept in localStorage per case; retried on `online`.
"use client";

import { useEffect, useState } from "react";

import { ApiError, post, type ManualVitalsRequest } from "@/lib/api";
import { toast } from "@/lib/toast";

const key = (caseId: string, kind: string) => `atollcare.${kind}.${caseId}`;

function read<T>(k: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(k);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(k: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(k);
    else localStorage.setItem(k, JSON.stringify(value));
  } catch {
    // storage unavailable
  }
}

export const loadDraftText = (caseId: string) => read<string>(key(caseId, "draft"), "");
export const saveDraftText = (caseId: string, text: string) => write(key(caseId, "draft"), text || null);

export function queuedVitals(caseId: string): ManualVitalsRequest[] {
  return read<ManualVitalsRequest[]>(key(caseId, "queue"), []);
}

export function queueVitals(caseId: string, req: ManualVitalsRequest) {
  write(key(caseId, "queue"), [...queuedVitals(caseId), { ...req, recorded_at: req.recorded_at ?? new Date().toISOString() }]);
}

/** POST vitals; on network failure queue them locally. Returns true if sent now. */
export async function sendVitals(caseId: string, req: ManualVitalsRequest): Promise<boolean> {
  try {
    await post(`/cases/${caseId}/vitals`, req);
    return true;
  } catch (err) {
    if (err instanceof ApiError && err.code === "network") {
      queueVitals(caseId, req);
      toast("Offline — vitals saved and will send when connected", "warn");
      return false;
    }
    throw err;
  }
}

export async function flushQueue(caseId: string): Promise<number> {
  const queue = queuedVitals(caseId);
  let sent = 0;
  for (const req of queue) {
    try {
      await post(`/cases/${caseId}/vitals`, req);
      sent++;
    } catch {
      break;
    }
  }
  write(key(caseId, "queue"), queue.slice(sent).length ? queue.slice(sent) : null);
  if (sent) toast(`Back online — sent ${sent} queued reading${sent > 1 ? "s" : ""}`, "info");
  return sent;
}

export function useOnline(caseId?: string, onFlushed?: () => void) {
  const [online, setOnline] = useState(() => (typeof navigator === "undefined" ? true : navigator.onLine));
  const [pending, setPending] = useState(0);
  useEffect(() => {
    if (!caseId) return;
    const up = async () => {
      setOnline(true);
      await flushQueue(caseId);
      setPending(queuedVitals(caseId).length);
      onFlushed?.();
    };
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    const t = setInterval(() => {
      setPending(queuedVitals(caseId).length);
      setOnline(navigator.onLine);
    }, 2000);
    if (navigator.onLine && queuedVitals(caseId).length) up();
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
      clearInterval(t);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caseId]);
  return { online, pending };
}
