// F-M1.2–F-M1.10 Reporter / island-clinician case page (mobile-first).
"use client";

import { AlertTriangle, Send, WifiOff } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { twMerge } from "tailwind-merge";

import ButtonDanger from "@/app/components/(buttons)/ButtonDanger";
import CaseHeadline from "@/app/components/(case)/CaseHeadline";
import CaseTimeline from "@/app/components/(case)/CaseTimeline";
import FamilyStatus from "@/app/components/(case)/FamilyStatus";
import RouteCard from "@/app/components/(case)/RouteCard";
import PillSeverity from "@/app/components/(pills)/PillSeverity";
import PillStatus from "@/app/components/(pills)/PillStatus";
import Skeleton from "@/app/components/Skeleton";
import { post, type Case } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";
import { facilityName, SEVERITY_LABEL } from "@/lib/format";
import { useOnline } from "@/lib/offline";
import { useRole } from "@/lib/role";
import { useCase, useMeta } from "@/lib/swr";
import { useEventToasts } from "@/lib/useEventToasts";

import styles from "../Report.module.scss";
import DescribePanel from "./DescribePanel";
import GuidancePanel from "./GuidancePanel";
import InfoRequestPanel from "./InfoRequestPanel";
import PatientPanel from "./PatientPanel";
import ReferralPanel from "./ReferralPanel";
import VitalsPanel from "./VitalsPanel";

const LANG_KEY = "atollcare.lang";

export default function ({ caseId }: { caseId: string }) {
  const { data: c, error, mutate } = useCase(caseId);
  const { data: meta } = useMeta();
  const role = useRole();
  const { busy, run } = useCaseAction(caseId);
  const { online, pending } = useOnline(caseId, () => mutate());
  const [language, setLanguage] = useState("en");
  useEventToasts(c);

  useEffect(() => {
    try {
      setLanguage(localStorage.getItem(LANG_KEY) ?? "en");
    } catch {
      // ignore
    }
  }, []);
  const changeLanguage = (l: string) => {
    setLanguage(l);
    try {
      localStorage.setItem(LANG_KEY, l);
    } catch {
      // ignore
    }
  };

  if (error && !c) {
    return (
      <p className="py-[2rem] text-center">
        Case not found. <Link href="/report" className="text-brand underline">Raise a new alert</Link>
      </p>
    );
  }
  if (!c || !meta) {
    return (
      <div className="mx-auto flex max-w-[48rem] flex-col gap-[1rem]">
        <Skeleton className="h-[4rem]" />
        <Skeleton className="h-[12rem]" />
        <Skeleton className="h-[12rem]" />
      </div>
    );
  }

  const rec = c.recommendation;
  const clinician = role === "clinician";
  const severe = rec && (rec.severity === "critical" || rec.severity === "high");

  return (
    <div className="mx-auto flex max-w-[48rem] flex-col gap-[1rem]">
      {(!online || pending > 0) && (
        <div className={twMerge(styles.banner, "bg-warn-soft text-warn-fg")}>
          <WifiOff size={20} /> {online ? `Sending ${pending} queued reading(s)…` : "Offline — will send when connected"}
        </div>
      )}

      <header className="flex flex-wrap items-end justify-between gap-[1rem]">
        <div>
          <p className="text-[0.875rem] text-muted">Case code — read this over the phone</p>
          <p className={styles.code}>{c.short_code}</p>
          <p className="mt-[.25rem] text-[0.875rem] text-muted">{facilityName(meta.facilities, c.origin_facility_id)}</p>
        </div>
        <PillStatus status={c.status} />
      </header>

      {rec && (
        <div
          className={twMerge(
            styles.banner,
            severe ? "bg-alert text-white" : rec.severity === "low" ? "bg-surface" : "bg-warn-soft text-warn-fg",
          )}
        >
          <AlertTriangle size={24} />
          <span>
            {SEVERITY_LABEL[rec.severity]} severity — {facilityName(meta.facilities, rec.destination_id)} recommended
          </span>
          <PillSeverity severity={rec.severity} className="ml-auto hidden sm:inline-flex" />
        </div>
      )}
      {rec && <CaseHeadline headline={c.headline} />}

      <InfoRequestPanel c={c} />

      <DescribePanel c={c} language={language} />
      <PatientPanel c={c} />
      <VitalsPanel
        c={c}
        scanEnabled={meta.adapters.presage !== "manual"}
        speed={meta.demo_state.speed_multiplier}
        clinician={clinician}
      />

      {c.status === "draft" && (
        <ButtonDanger
          className="min-h-[3.5rem] text-[1.125rem]"
          disabled={busy}
          onClick={() => run(() => post<Case>(`/cases/${c.id}/submit`))}
        >
          <Send size={20} /> {busy ? "Sending…" : "Send to doctor"}
        </ButtonDanger>
      )}

      {rec && <RouteCard rec={rec} facilities={meta.facilities} />}
      {(c.intake || rec) && <GuidancePanel c={c} role={clinician ? "clinician" : "reporter"} language={language} onLanguage={changeLanguage} />}
      {rec && clinician && <ReferralPanel c={c} facilities={meta.facilities} />}
      {rec && !clinician && !c.referral && (
        <p className="rounded-[.75rem] bg-surface p-[1rem] text-[0.875rem] text-muted">
          The island clinician sends the referral. Switch role to <strong>Island clinician</strong> in the header to continue.
        </p>
      )}
      {c.status !== "draft" && <FamilyStatus c={c} now={meta.now} />}
      <CaseTimeline events={c.timeline} now={meta.now} />
    </div>
  );
}
