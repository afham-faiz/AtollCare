// §3 Role switcher (no real auth) — stored in localStorage, sent as X-Role for timeline attribution.
"use client";

import { useSyncExternalStore } from "react";

export const ROLES = [
  { id: "reporter", label: "Reporter" },
  { id: "clinician", label: "Island clinician" },
  { id: "specialist", label: "Specialist" },
  { id: "transport", label: "Transport" },
  { id: "demo", label: "Demo operator" },
] as const;

export type Role = (typeof ROLES)[number]["id"];
const KEY = "atollcare.role";
const listeners = new Set<() => void>();

export function getRole(): Role {
  if (typeof window === "undefined") return "reporter";
  try {
    const value = window.localStorage.getItem(KEY);
    return (ROLES.find((r) => r.id === value)?.id ?? "reporter") as Role;
  } catch {
    return "reporter";
  }
}

export function setRole(role: Role) {
  try {
    window.localStorage.setItem(KEY, role);
  } catch {
    // storage unavailable — role stays in memory for this render only
  }
  listeners.forEach((l) => l());
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("storage", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", cb);
  };
}

export function useRole(): Role {
  return useSyncExternalStore(subscribe, getRole, () => "reporter");
}
