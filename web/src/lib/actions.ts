// Mutation helper: busy state, toast on error, write the returned Case into the SWR cache.
"use client";

import { useState } from "react";
import { mutate } from "swr";

import type { Case } from "@/lib/api";
import { toastError } from "@/lib/toast";

export function useCaseAction(caseId?: string) {
  const [busy, setBusy] = useState(false);
  const run = async <T,>(fn: () => Promise<T>): Promise<T | undefined> => {
    setBusy(true);
    try {
      const result = await fn();
      if (caseId && result && typeof result === "object" && "short_code" in (result as object)) {
        await mutate(`/cases/${caseId}`, result as unknown as Case, { revalidate: false });
      } else if (caseId) {
        await mutate(`/cases/${caseId}`);
      }
      await mutate((key) => typeof key === "string" && key.startsWith("/cases?"));
      return result;
    } catch (err) {
      toastError(err);
      return undefined;
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}
