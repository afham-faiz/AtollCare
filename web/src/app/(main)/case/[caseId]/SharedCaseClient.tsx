// F-M1.8 Family view: status stepper, ETA, spoken update, map. Read-only, mobile-first, no clinical detail.
"use client";

import CaseHeadline from "@/app/components/(case)/CaseHeadline";
import FamilyStatus from "@/app/components/(case)/FamilyStatus";
import AtollMapLazy from "@/app/components/(map)/AtollMapLazy";
import Skeleton from "@/app/components/Skeleton";
import { facilityName } from "@/lib/format";
import { useCase, useMeta, useTrack } from "@/lib/swr";

export default function ({ caseId }: { caseId: string }) {
  const { data: c, error } = useCase(caseId);
  const { data: meta } = useMeta();
  const { data: track } = useTrack(caseId, !!c && c.transport.status !== "none");
  if (error && !c) return <p className="py-[2rem] text-center">This link is no longer valid.</p>;
  if (!c || !meta) return <Skeleton className="mx-auto h-[20rem] max-w-[36rem]" />;
  const dest = c.referral?.destination_id ?? c.recommendation?.destination_id;
  const route = c.transport.route ?? c.recommendation?.alternatives.find((r) => r.id === c.recommendation?.chosen_route_id) ?? null;
  return (
    <div className="mx-auto flex max-w-[36rem] flex-col gap-[1rem]">
      <header>
        <p className="text-[0.875rem] text-muted">Case</p>
        <h1 className="text-[2.25rem] font-extrabold tracking-[0.06em] tabular-nums">{c.short_code}</h1>
        <p className="text-[0.9375rem]">
          From {facilityName(meta.facilities, c.origin_facility_id)}
          {dest && <> to {facilityName(meta.facilities, dest)}</>}
        </p>
      </header>
      <FamilyStatus c={c} now={meta.now} showShare={false} />
      {c.recommendation && <CaseHeadline headline={c.headline} />}
      <AtollMapLazy
        facilities={meta.facilities}
        height="18rem"
        cases={[{ id: c.id, label: c.short_code, originId: c.origin_facility_id, destinationId: dest, route, track, highlight: true }]}
      />
      <p className="text-[0.875rem] text-muted">
        Updates every few seconds. For medical questions, contact the health centre caring for your family member.
      </p>
    </div>
  );
}
