// F-M3.2 Case review: SBAR, intake, NEWS2, vitals trend + forecast, route + map, timeline, actions.
"use client";

import { ArrowLeft, CheckCircle2, MessageSquare } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import CaseHeadline from "@/app/components/(case)/CaseHeadline";
import CaseTimeline from "@/app/components/(case)/CaseTimeline";
import EngineInspector from "@/app/components/(case)/EngineInspector";
import IntakeChips from "@/app/components/(case)/IntakeChips";
import News2Card from "@/app/components/(case)/News2Card";
import RouteCard from "@/app/components/(case)/RouteCard";
import SbarSummary from "@/app/components/(case)/SbarSummary";
import TimeSavedPanel from "@/app/components/(case)/TimeSavedPanel";
import VitalsChart from "@/app/components/(case)/VitalsChart";
import AtollMapLazy from "@/app/components/(map)/AtollMapLazy";
import Card from "@/app/components/Card";
import PillStatus from "@/app/components/(pills)/PillStatus";
import Skeleton from "@/app/components/Skeleton";
import { post, type Case } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";
import { facilityName, fmtTime } from "@/lib/format";
import { useRole } from "@/lib/role";
import { useCase, useMeta, useTrack, useTrend } from "@/lib/swr";
import { useEventToasts } from "@/lib/useEventToasts";

import styles from "../Hospital.module.scss";
import ResponseActions from "./ResponseActions";

export default function ({ caseId }: { caseId: string }) {
  const { data: c, error } = useCase(caseId);
  const { data: meta } = useMeta();
  const { data: trend } = useTrend(caseId);
  const moving = c ? ["dispatched", "in_transit", "arrived"].includes(c.transport.status) : false;
  const { data: track } = useTrack(caseId, moving);
  const role = useRole();
  const { busy, run } = useCaseAction(caseId);
  const [note, setNote] = useState("");
  const [outcome, setOutcome] = useState("");
  useEventToasts(c);

  if (error && !c) return <p className="py-[2rem] text-center">Case not found.</p>;
  if (!c || !meta) return <Skeleton className="h-[20rem]" />;

  const rec = c.recommendation;
  const route = c.transport.route ?? rec?.alternatives.find((r) => r.id === rec.chosen_route_id) ?? null;
  const dest = c.referral?.destination_id ?? rec?.destination_id;

  return (
    <div className="flex flex-col gap-[1rem]">
      <Link href="/hospital" className="inline-flex min-h-[2.75rem] items-center gap-[.25rem] text-[0.875rem] text-brand">
        <ArrowLeft size={16} /> Inbox
      </Link>
      <header className="flex flex-wrap items-center gap-[.75rem]">
        <h1 className="text-[1.75rem] font-bold tabular-nums">{c.short_code}</h1>
        <PillStatus status={c.status} />
        <span className="text-muted">
          {facilityName(meta.facilities, c.origin_facility_id)} → {facilityName(meta.facilities, dest)}
          {c.referral?.responder_name && ` · ${c.referral.response} by ${c.referral.responder_name}`}
        </span>
      </header>
      <CaseHeadline headline={c.headline} />
      {c.status === "arrived" && (
        <div className="flex items-center gap-[.5rem] rounded-[.75rem] bg-brand p-[1rem] font-semibold text-brand-fg">
          <CheckCircle2 size={24} /> Arrived at {facilityName(meta.facilities, dest)} {fmtTime(c.meta.arrived_at)} — ready for handover
        </div>
      )}

      <div className="grid gap-[1rem] lg:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-[1rem]">
          <SbarSummary sbar={c.referral?.sbar} />
          {c.referral && (c.referral.info_answers.length > 0 || c.referral.info_requests.length > 0) && (
            <Card title="Info Q&A">
              <ul className="flex flex-col gap-[.5rem] text-[0.9375rem]">
                {c.referral.info_answers.map((a, i) => (
                  <li key={i}>
                    <p className="text-muted">Q: {a.question}</p>
                    <p>A: {a.answer} <span className="text-[0.875rem] text-muted">· {fmtTime(a.at)}</span></p>
                  </li>
                ))}
                {c.referral.info_requests.map((q) => (
                  <li key={q} className="text-warn-fg">Q: {q} — awaiting answer</li>
                ))}
              </ul>
            </Card>
          )}
          <IntakeChips intake={c.intake} />
          <News2Card news2={c.news2} />
          <VitalsChart trend={trend} />
        </div>
        <div className="flex min-w-0 flex-col gap-[1rem]">
          {rec ? <RouteCard rec={rec} facilities={meta.facilities} /> : <Card title="Recommended route"><p className="text-muted">Not assessed yet.</p></Card>}
          <AtollMapLazy
            facilities={meta.facilities}
            height="18rem"
            cases={[{ id: c.id, label: c.short_code, originId: c.origin_facility_id, destinationId: dest, route, track, highlight: true }]}
          />
          {rec && <TimeSavedPanel baseline={rec.baseline} />}
          <EngineInspector c={c} facilities={meta.facilities} />
        </div>
      </div>

      <Card title="Notes & close">
        <div className="flex flex-col gap-[.75rem]">
          <label className={styles.field}>
            <span>Add a note to the timeline</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} className="min-h-[4rem]" />
          </label>
          <ButtonBase
            disabled={busy || !note.trim()}
            onClick={async () => {
              const r = await run(() => post<Case>(`/cases/${c.id}/notes`, { text: note, actor_role: role }));
              if (r) setNote("");
            }}
          >
            <MessageSquare size={20} /> Add note
          </ButtonBase>
          {c.status !== "closed" && (
            <div className="flex flex-col gap-[.5rem] border-t-[1px] border-border pt-[.75rem]">
              <label className={styles.field}>
                <span>Outcome note (closing the case shows final time vs baseline)</span>
                <input value={outcome} onChange={(e) => setOutcome(e.target.value)} />
              </label>
              <ButtonPrimary disabled={busy} onClick={() => run(() => post<Case>(`/cases/${c.id}/close`, { outcome_note: outcome }))}>
                Close case
              </ButtonPrimary>
            </div>
          )}
          {c.status === "closed" && <p className="font-medium">Closed. {c.meta.outcome_note}</p>}
        </div>
      </Card>

      <CaseTimeline events={c.timeline} now={meta.now} />
      <ResponseActions c={c} />
    </div>
  );
}
