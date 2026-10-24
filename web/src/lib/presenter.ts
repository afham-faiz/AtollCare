// Presenter tools are kept out of the clinical UI: opened with ⌘/Ctrl + . or the discreet button in the top bar.
"use client";

import { useEffect, useSyncExternalStore } from "react";

let open = false;
const listeners = new Set<() => void>();

export function setPresenterOpen(v: boolean) {
  open = v;
  listeners.forEach((l) => l());
}

export function usePresenterOpen(): boolean {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => open,
    () => false,
  );
}

export function usePresenterShortcut() {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === ".") {
        e.preventDefault();
        setPresenterOpen(!open);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
