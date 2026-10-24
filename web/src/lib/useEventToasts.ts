// F-M3.5 Toast newly arrived re-plan events ("Re-routed to Hithadhoo Regional: IGMH cath lab unavailable").
"use client";

import { useEffect, useRef } from "react";

import type { Case } from "@/lib/api";
import { toast } from "@/lib/toast";

export function useEventToasts(c?: Case) {
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!c) return;
    if (seen.current === null) {
      seen.current = new Set(c.timeline.map((e) => e.id));
      return;
    }
    for (const e of c.timeline) {
      if (seen.current.has(e.id)) continue;
      seen.current.add(e.id);
      if ((e.data as Record<string, unknown>)?.toast || e.type === "declined") toast(e.summary, "warn", 8000);
    }
  }, [c]);
}
