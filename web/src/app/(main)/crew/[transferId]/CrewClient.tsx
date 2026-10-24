// Crew monitor (tablet/laptop on a mount): camera + Presage, live vitals, one voice button, hospital messages read
// aloud. Everything else lives on the hospital screen.
"use client";

import { Activity, Flag, HeartPulse, Plus, Volume2, VolumeX, Wind } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import AlertBanner from "@/app/components/(transfer)/AlertBanner";
import EtaBar from "@/app/components/(transfer)/EtaBar";
import StatusPill from "@/app/components/(transfer)/StatusPill";
import Timeline from "@/app/components/(transfer)/Timeline";
import VitalTile, { type Tone } from "@/app/components/(transfer)/VitalTile";
import Card from "@/app/components/Card";
import Skeleton from "@/app/components/Skeleton";
import { post, type MonitoringSource, type Note, type Transfer } from "@/lib/api";
import { NEWS2_LABEL, num, patientLine } from "@/lib/format";
import { useCamera, usePresage } from "@/lib/presage";
import { speak, stopSpeaking } from "@/lib/speech";
import { useMeta, useTransfer } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import BreathingWave from "./BreathingWave";
import CameraPanel from "./CameraPanel";
import ManualVitalsModal from "./ManualVitalsModal";
import VoiceBar from "./VoiceBar";

const PRESAGE_HR_MAX = 110; // Presage validated pulse range 40–110 BPM
const CONVERSATION = new Set(["voice", "text", "answer", "question", "message"]);

function hrTone(v: number | null): Tone {
  if (v === null) return "muted";
  if (v >= 131 || v <= 40) return "alert";
  if (v >= 111 || v <= 50) return "warn";
  return "normal";
}

function rrTone(v: number | null): Tone {
  if (v === null) return "muted";
  if (v >= 25 || v <= 8) return "alert";
  if (v >= 21) return "warn";
  return "normal";
}

export default function ({ transferId }: { transferId: string }) {
  const { data: t, error } = useTransfer(transferId);
  const { data: meta } = useMeta();
  const region = meta?.regions.find((r) => r.id === t?.region_id);
  const [voiceOn, setVoiceOn] = useState(true);
  const [vitalsOpen, setVitalsOpen] = useState(false);

  // camera + Presage bridge
  const active = !!t && (t.status === "pending" || t.status === "accepted");
  const cam = useCamera(active);
  const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null);
  const videoRef = useCallback(
    (el: HTMLVideoElement | null) => {
      cam.videoRef.current = el;
      setVideoEl(el);
    },
    [cam.videoRef],
  );
  const presage = usePresage(active ? transferId : undefined, videoEl, cam.camera === "on");
  const live = presage.state === "running" && cam.camera === "on";

  // keep the engine's monitoring source in step: real Presage when measuring, labelled simulation otherwise
  const requested = useRef<MonitoringSource | null>(null);
  useEffect(() => {
    if (!t || !active) return;
    const settled = cam.camera === "on" ? presage.state !== "starting" : cam.camera !== "starting";
    if (!settled) return;
    const want: MonitoringSource = live ? "presage" : "simulated";
    if (t.monitoring.source === want || requested.current === want) return;
    requested.current = want;
    post(`/transfers/${transferId}/monitoring`, { source: want }).catch(() => (requested.current = null));
  }, [t, active, live, cam.camera, presage.state, transferId]);

  // speak new hospital messages and alerts once
  const seen = useRef<Set<string> | null>(null);
  useEffect(() => {
    if (!t) return;
    if (seen.current === null) {
      seen.current = new Set(t.notes.map((n) => n.id));
      return;
    }
    for (const n of t.notes) {
      if (seen.current.has(n.id)) continue;
      seen.current.add(n.id);
      if (!voiceOn) continue;
      if (n.author === "hospital") speak(n.kind === "question" ? `Question from ${n.text}` : n.text, "hospital");
      if (n.kind === "alert") speak(`Alert. ${n.text}`, "hospital");
    }
  }, [t, voiceOn]);

  const openQuestion: Note | null = useMemo(() => {
    if (!t) return null;
    const answered = new Set(t.notes.filter((n) => n.reply_to).map((n) => n.reply_to));
    return [...t.notes].reverse().find((n) => n.kind === "question" && !answered.has(n.id)) ?? null;
  }, [t]);
  const lastHospital = useMemo(() => (t ? [...t.notes].reverse().find((n) => n.author === "hospital") : undefined), [t]);

  const refresh = (next?: Transfer) => mutate(`/transfers/${transferId}`, next, { revalidate: !next });

  if (error && !t) {
    return (
      <p className="py-[3rem] text-center">
        Transfer not found. <Link href="/crew" className="text-brand underline">Start a new one</Link>
      </p>
    );
  }
  if (!t || !meta) {
    return (
      <div className="grid gap-[1rem] lg:grid-cols-[3fr_2fr]">
        <Skeleton className="aspect-[16/9] w-full" />
        <Skeleton className="h-[20rem]" />
      </div>
    );
  }

  const hr = live && presage.metrics.hr ? presage.metrics.hr.value : num(t.latest.heart_rate?.value);
  const rr = live && presage.metrics.rr ? presage.metrics.rr.value : num(t.latest.resp_rate?.value);
  const hrv = live && presage.metrics.hrv ? presage.metrics.hrv.value : num(t.latest.hrv_rmssd?.value);
  const hrStable = live ? !!presage.metrics.hr?.stable : true;
  const rrStable = live ? !!presage.metrics.rr?.stable : true;
  const sourceNote = live ? "Presage camera" : t.monitoring.source === "simulated" ? "Simulated" : "—";
  const n2 = t.news2;
  const n2Tone: Tone = !n2?.total ? "muted" : n2.total >= 7 ? "alert" : n2.total >= 5 || n2.any_single_3 ? "warn" : "normal";
  const spo2 = num(t.latest.spo2?.value);
  const sbp = num(t.latest.systolic_bp?.value);
  const temp = num(t.latest.temperature_c?.value);
  const acvpu = t.latest.consciousness?.value;
  const done = t.status === "arrived" || t.status === "closed";

  const arrive = async () => {
    try {
      refresh(await post<Transfer>(`/transfers/${transferId}/arrive`));
    } catch (err) {
      toastError(err);
    }
  };

  return (
    <div className="flex flex-col gap-[1rem]">
      <header className="flex flex-wrap items-center gap-x-[1rem] gap-y-[.5rem]">
        <h1 className="text-[1.75rem] font-bold tabular-nums">{t.code}</h1>
        <span className="text-[1.0625rem]">
          {patientLine(t.patient)} · <span className="text-muted">{t.complaint}</span>
        </span>
        <StatusPill status={t.status} />
        <span className="ml-auto flex gap-[.5rem]">
          <ButtonBase
            onClick={() => {
              if (voiceOn) stopSpeaking();
              setVoiceOn(!voiceOn);
            }}
            aria-pressed={voiceOn}
            title="Read hospital messages and alerts aloud"
          >
            {voiceOn ? <Volume2 size={18} /> : <VolumeX size={18} />} {voiceOn ? "Voice on" : "Voice off"}
          </ButtonBase>
          {!done && (
            <ButtonBase onClick={arrive}>
              <Flag size={18} /> Arrived
            </ButtonBase>
          )}
        </span>
      </header>

      <EtaBar t={t} region={region} now={meta.now} />
      <AlertBanner alerts={t.alerts} />

      {lastHospital && !done && (
        <div className={twMerge("flex items-start gap-[.75rem] rounded-[.75rem] px-[1rem] py-[.75rem]", openQuestion ? "bg-info text-white" : "border-[1px] border-info/30 bg-info-soft text-info")}>
          <Volume2 size={20} className="mt-[.125rem] shrink-0" />
          <p className="text-[1.0625rem] font-medium">{(openQuestion ?? lastHospital).text}</p>
        </div>
      )}

      <div className="grid gap-[1rem] lg:grid-cols-[3fr_2fr]">
        <CameraPanel videoRef={videoRef} camera={cam.camera} presage={presage.state} hint={presage.hint} message={presage.message} />

        <div className="grid grid-cols-2 content-start gap-[.75rem]">
          <VitalTile
            label="Heart rate"
            icon={<HeartPulse size={18} className={twMerge(hr !== null && "animate-beat text-alert")} />}
            value={hr !== null ? Math.round(hr) : "—"}
            unit="bpm"
            size="lg"
            tone={hrStable ? hrTone(hr) : "muted"}
            note={live && hr !== null && hr > PRESAGE_HR_MAX ? "Above validated range — confirm manually" : live && !hrStable ? "Measuring…" : sourceNote}
          />
          <VitalTile
            label="Breathing"
            icon={<Wind size={18} />}
            value={rr !== null ? Math.round(rr) : "—"}
            unit="/min"
            size="lg"
            tone={rrStable ? rrTone(rr) : "muted"}
            note={live && !rrStable ? "Settling (needs 30 s still)" : sourceNote}
          >
            {live && <BreathingWave trace={presage.metrics.trace} className="mt-[.25rem] h-[2rem] w-full" />}
          </VitalTile>
          <VitalTile
            label="NEWS2"
            icon={<Activity size={18} />}
            value={n2?.total ?? "—"}
            tone={n2Tone}
            note={n2?.band ? `${NEWS2_LABEL[n2.band]}${n2.complete ? "" : " · partial"}` : "Needs vitals"}
          />
          <VitalTile label="HRV" value={hrv !== null ? Math.round(hrv) : "—"} unit="ms" tone={hrv === null ? "muted" : "normal"} note="RMSSD" />
          <button type="button" onClick={() => setVitalsOpen(true)} className="col-span-2 flex min-h-[3.5rem] items-center justify-between gap-[.75rem] rounded-[.75rem] border-[1px] border-dashed border-border bg-surface px-[1rem] text-left hover:border-brand">
            <span className="flex flex-wrap gap-x-[1rem] text-[0.9375rem] tabular-nums">
              <span>SpO₂ <strong>{spo2 ?? "—"}</strong></span>
              <span>BP <strong>{sbp ?? "—"}</strong></span>
              <span>T <strong>{temp ?? "—"}</strong></span>
              <span>ACVPU <strong>{acvpu ? String(acvpu) : "—"}</strong></span>
            </span>
            <span className="flex shrink-0 items-center gap-[.25rem] font-medium text-brand-strong">
              <Plus size={18} /> Add
            </span>
          </button>
        </div>
      </div>

      {!done && (
        <VoiceBar
          transferId={transferId}
          serverStt={meta.adapters.elevenlabs === "real"}
          question={openQuestion}
          onSaved={(next) => refresh(next)}
        />
      )}

      <Card title="Notes and messages">
        <Timeline notes={t.notes.filter((n) => CONVERSATION.has(n.kind))} tz={region?.timezone} limit={5} />
      </Card>

      <ManualVitalsModal transferId={transferId} open={vitalsOpen} onClose={() => setVitalsOpen(false)} onSaved={() => refresh()} />
    </div>
  );
}
