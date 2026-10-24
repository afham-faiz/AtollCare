// Selected transfer: who is coming and when, live vitals, briefing, trend, questions, timeline. Two actions.
"use client";

import { Check, MessageCircleQuestion } from "lucide-react";
import { useState } from "react";
import { mutate } from "swr";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import AlertBanner from "@/app/components/(transfer)/AlertBanner";
import BriefingCard from "@/app/components/(transfer)/BriefingCard";
import EtaBar from "@/app/components/(transfer)/EtaBar";
import StatusPill from "@/app/components/(transfer)/StatusPill";
import Timeline from "@/app/components/(transfer)/Timeline";
import TransferMapLazy from "@/app/components/(transfer)/TransferMapLazy";
import TrendChart from "@/app/components/(transfer)/TrendChart";
import VitalTile, { type Tone } from "@/app/components/(transfer)/VitalTile";
import Card from "@/app/components/Card";
import Skeleton from "@/app/components/Skeleton";
import type { LatestValue, Transfer } from "@/lib/api";
import { ago, NEWS2_LABEL, num, patientLine } from "@/lib/format";
import { useMeta, useTransfer, useTrend } from "@/lib/swr";

import AcceptModal from "./AcceptModal";
import AskModal from "./AskModal";

const SOURCE: Record<string, string> = { presage: "camera", manual: "crew", simulated: "simulated" };

function tile(lv: LatestValue | undefined, now: string, tone: (v: number) => Tone) {
  const v = num(lv?.value);
  return {
    value: v ?? (lv ? String(lv.value) : "—"),
    tone: v === null ? ("muted" as Tone) : tone(v),
    note: lv ? (lv.flag ? "confirm manually" : `${SOURCE[lv.source]} · ${ago(lv.at, now)}`) : "not recorded",
  };
}

export default function ({ transferId }: { transferId: string }) {
  const { data: t } = useTransfer(transferId);
  const { data: meta } = useMeta();
  const { data: trend } = useTrend(transferId);
  const [modal, setModal] = useState<"accept" | "ask" | null>(null);

  if (!t || !meta) return <Skeleton className="h-[30rem]" />;
  const region = meta.regions.find((r) => r.id === t.region_id);
  const tz = region?.timezone;
  const L = t.latest;
  const now = meta.now;
  const hr = tile(L.heart_rate, now, (v) => (v >= 131 || v <= 40 ? "alert" : v >= 111 || v <= 50 ? "warn" : "normal"));
  const rr = tile(L.resp_rate, now, (v) => (v >= 25 || v <= 8 ? "alert" : v >= 21 ? "warn" : "normal"));
  const spo2 = tile(L.spo2, now, (v) => (v <= 91 ? "alert" : v <= 95 ? "warn" : "normal"));
  const sbp = tile(L.systolic_bp, now, (v) => (v <= 90 || v >= 220 ? "alert" : v <= 110 ? "warn" : "normal"));
  const temp = tile(L.temperature_c, now, (v) => (v <= 35 || v >= 39.1 ? "alert" : v <= 36 || v >= 38.1 ? "warn" : "normal"));
  const n2 = t.news2;
  const n2Tone: Tone = !n2?.total ? "muted" : n2.total >= 7 ? "alert" : n2.total >= 5 || n2.any_single_3 ? "warn" : "normal";
  const answers = new Map(t.notes.filter((n) => n.reply_to).map((n) => [n.reply_to, n]));
  const questions = t.notes.filter((n) => n.kind === "question");
  const active = t.status === "pending" || t.status === "accepted";
  const refresh = (next: Transfer) => {
    mutate(`/transfers/${transferId}`, next, { revalidate: false });
    mutate((k) => typeof k === "string" && k.startsWith("/transfers?"));
    mutate("/transfers");
  };

  return (
    <div className="flex flex-col gap-[1rem]">
      <header className="flex flex-wrap items-center gap-x-[1rem] gap-y-[.5rem]">
        <h2 className="text-[1.75rem] font-bold tabular-nums">{t.code}</h2>
        <span className="text-[1.0625rem]">
          {patientLine(t.patient)} · <strong>{t.briefing?.suspected_condition ?? t.complaint}</strong>
        </span>
        <StatusPill status={t.status} />
        {active && (
          <span className="ml-auto flex gap-[.5rem]">
            <ButtonBase onClick={() => setModal("ask")}>
              <MessageCircleQuestion size={18} /> Ask crew
            </ButtonBase>
            {t.status === "pending" && (
              <ButtonPrimary onClick={() => setModal("accept")}>
                <Check size={18} /> Accept
              </ButtonPrimary>
            )}
          </span>
        )}
      </header>
      {t.acceptance && (
        <p className="-mt-[.5rem] text-[0.9375rem] text-brand-strong">
          Accepted by {t.acceptance.by}
          {t.acceptance.prepare.length ? ` · preparing ${t.acceptance.prepare.join(", ").toLowerCase()}` : ""}
        </p>
      )}

      <EtaBar t={t} region={region} now={now} />
      <AlertBanner alerts={t.alerts} />

      <div className="grid grid-cols-2 gap-[.75rem] sm:grid-cols-3 xl:grid-cols-6">
        <VitalTile label="Heart rate" unit="bpm" {...hr} />
        <VitalTile label="Breathing" unit="/min" {...rr} />
        <VitalTile label="SpO₂" unit="%" {...spo2} />
        <VitalTile label="Systolic BP" unit="mmHg" {...sbp} />
        <VitalTile label="Temp" unit="°C" {...temp} />
        <VitalTile
          label="NEWS2"
          value={n2?.total ?? "—"}
          tone={n2Tone}
          note={n2?.band ? `${NEWS2_LABEL[n2.band]}${n2.complete ? "" : " · partial"}` : "needs vitals"}
        />
      </div>

      <div className="grid gap-[1rem] xl:grid-cols-2">
        <div className="flex min-w-0 flex-col gap-[1rem]">
          <BriefingCard briefing={t.briefing} now={now} />
          {questions.length > 0 && (
            <Card title="Questions to the crew">
              <ul className="flex flex-col gap-[.75rem]">
                {questions.map((q) => {
                  const a = answers.get(q.id);
                  return (
                    <li key={q.id}>
                      <p className="text-[0.9375rem] text-info">{q.text}</p>
                      <p className={a ? "text-[0.9375rem] font-medium" : "text-[0.9375rem] text-muted"}>
                        {a ? `↳ ${a.text}` : "↳ waiting for the crew…"}
                      </p>
                    </li>
                  );
                })}
              </ul>
            </Card>
          )}
        </div>
        <div className="flex min-w-0 flex-col gap-[1rem]">
          <TrendChart trend={trend} tz={tz} />
          <TransferMapLazy t={t} region={region} />
        </div>
      </div>

      <Card title="Timeline">
        <Timeline notes={t.notes} tz={tz} />
      </Card>

      <AcceptModal t={t} open={modal === "accept"} onClose={() => setModal(null)} options={meta.prepare_options} onDone={refresh} />
      <AskModal t={t} open={modal === "ask"} onClose={() => setModal(null)} onDone={refresh} />
    </div>
  );
}
