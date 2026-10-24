// F-M8.4 Presenter view: phone frame (report page iframe) + hospital iframe + live map, side by side.
"use client";

import Link from "next/link";

import CaseHeadline from "@/app/components/(case)/CaseHeadline";
import AtollMapLazy from "@/app/components/(map)/AtollMapLazy";
import type { MetaResponse } from "@/lib/api";
import { useCase, useTrack } from "@/lib/swr";

import styles from "./Presenter.module.scss";

export default function ({ meta, caseId }: { meta: MetaResponse; caseId?: string }) {
  const { data: c } = useCase(caseId);
  const { data: track } = useTrack(caseId, !!c && c.transport.status !== "none");
  if (!caseId) {
    return (
      <p className="py-[2rem] text-center">
        Load a scenario first in <Link href="/demo" className="text-brand underline">/demo</Link>.
      </p>
    );
  }
  const rec = c?.recommendation;
  const route = c?.transport.route ?? rec?.alternatives.find((r) => r.id === rec.chosen_route_id) ?? null;
  return (
    <div className="flex flex-col gap-[.75rem]">
      <div className="flex items-center gap-[.75rem]">
        <Link href="/demo" className="text-[0.875rem] text-brand underline">Back to controls</Link>
        {c && <CaseHeadline headline={c.headline} className="flex-1" />}
      </div>
      <div className={styles.grid}>
        <div className={styles.phone}>
          <iframe src={`/report/${caseId}`} title="Island phone" />
        </div>
        <div className={styles.pane}>
          <iframe src={`/hospital/${caseId}`} title="Hospital" />
        </div>
        <div className={styles.map}>
          <AtollMapLazy
            facilities={meta.facilities}
            height="100%"
            cases={c ? [{ id: c.id, label: c.short_code, originId: c.origin_facility_id, destinationId: c.referral?.destination_id ?? rec?.destination_id, route, track, highlight: true }] : []}
          />
        </div>
      </div>
    </div>
  );
}
