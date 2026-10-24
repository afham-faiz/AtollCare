// F-M7.7 Tiny toast store (errors, re-plan notices).
"use client";

import { useSyncExternalStore } from "react";

import { ApiError } from "@/lib/api";

export type Toast = { id: number; text: string; tone: "info" | "error" | "warn" };
let toasts: Toast[] = [];
let seq = 0;
const listeners = new Set<() => void>();
const emit = () => listeners.forEach((l) => l());

export function toast(text: string, tone: Toast["tone"] = "info", ms = 5000) {
  const t = { id: ++seq, text, tone };
  toasts = [...toasts, t].slice(-4);
  emit();
  setTimeout(() => dismiss(t.id), ms);
}

export function dismiss(id: number) {
  toasts = toasts.filter((t) => t.id !== id);
  emit();
}

export function toastError(err: unknown) {
  const msg = err instanceof ApiError ? err.message : err instanceof Error ? err.message : "Something went wrong";
  toast(msg, "error", 7000);
}

export function useToasts(): Toast[] {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => toasts,
    () => toasts,
  );
}
