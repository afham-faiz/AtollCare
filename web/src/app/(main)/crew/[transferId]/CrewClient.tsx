// Crew monitor. Hierarchy: who → contactless assessment → vitals → note → next step. Contactless vitals come either
// from phone scans (Presage live for 30–60 s, the default on phones) or a continuous stream (a mounted tablet or laptop).
"use client";

import { ArrowUpRight, Check, CheckCircle2, Clock3, Flag, ListChecks, Smartphone, Volume2, VolumeX } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonGhost from "@/app/components/(buttons)/ButtonGhost";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import Segmented from "@/app/components/(controls)/Segmented";
import Sheet from "@/app/components/(modals)/Sheet";
import PreArrivalPanel from "@/app/components/(scan)/PreArrivalPanel";
import RouteLine from "@/app/components/(transfer)/RouteLine";
import StatusChip from "@/app/components/(transfer)/StatusChip";
import Timeline from "@/app/components/(transfer)/Timeline";
import Skeleton from "@/app/components/Skeleton";
import { post, type MonitoringSource, type Note, type Transfer } from "@/lib/api";
import { patientTitle } from "@/lib/clinical";
import { place } from "@/lib/format";
import { useCamera, usePresage } from "@/lib/presage";
import { speak, stopSpeaking } from "@/lib/speech";
import { useMeta, useTransfer } from "@/lib/swr";
import { toast, toastError } from "@/lib/toast";

import CameraInstrument, { instrumentPhase } from "./CameraInstrument";
import styles from "./Crew.module.scss";
import HandoffSheet from "./HandoffSheet";
import ScanStage from "./ScanStage";
import VitalsPanel from "./VitalsPanel";
import VitalsSheet from "./VitalsSheet";
import VoiceCapture from "./VoiceCapture";

type Mode = "scan" | "live";
const PHONE = "(max-width: 47.99rem)";

function useIsPhone(): boolean {
  return useSyncExternalStore(
    (onChange) => {
      const q = window.matchMedia(PHONE);
      q.addEventListener("change", onChange);
      return () => q.removeEventListener("change", onChange);
    },
    () => window.matchMedia(PHONE).matches,
    () => false,
  );
}

export default function ({ transferId }: { transferId: string }) {
  const router = useRouter();
  const { data: t, error } = useTransfer(transferId);
  const { data: meta } = useMeta();
  const region = meta?.regions.find((r) => r.id === t?.region_id);
  const [voiceOn, setVoiceOn] = useState(true);
  const [sheet, setSheet] = useState<null | "handoff" | "vitals" | "notes" | "packet">(null);
  const [justSent, setJustSent] = useState(false);
  const [startingDemo, setStartingDemo] = useState(false);

  // ── contactless instrument ────────────────────────────────────────────────
  const active = !!t && (t.status === "preparing" || t.status === "pending" || t.status === "accepted");
  // scans on a phone (or wherever this transfer already uses them); the live stream on a mounted tablet or laptop
  const phone = useIsPhone();
  const [chosen, setChosen] = useState<Mode | null>(null);
  const mode: Mode = chosen ?? (t?.monitoring.source === "scan" || phone ? "scan" : "live");
  const cam = useCamera(active && mode === "live");
  const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null);
  const videoRef = useCallback(
    (el: HTMLVideoElement | null) => {
      cam.videoRef.current = el;
      setVideoEl(el);
    },
    [cam.videoRef],
  );
  const presage = usePresage(active && mode === "live" ? transferId : undefined, videoEl, cam.camera === "on");
  const instrument = instrumentPhase(cam.camera, presage.state, presage.metrics);
  const live = instrument.phase === "acquiring" || instrument.phase === "measuring";

  // keep the engine's monitoring source honest: scans, or Presage while the live camera measures, or labelled
  // simulated (never scored) while it can't
  const requested = useRef<MonitoringSource | null>(null);
  useEffect(() => {
    if (!t || !active) return;
    if (mode === "live" && (instrument.phase === "connecting" || cam.camera === "starting")) return;
    const want: MonitoringSource = mode === "scan" ? "scan" : live ? "presage" : "simulated";
    if (t.monitoring.source === want || requested.current === want) return;
    requested.current = want;
    post(`/transfers/${transferId}/monitoring`, { source: want }).catch(() => (requested.current = null));
  }, [t, active, mode, live, instrument.phase, cam.camera, transferId]);

  // ── hospital → vehicle: speak new questions, messages and alerts once ─────
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
      if (n.author === "hospital" && voiceOn) speak(n.kind === "question" ? `Question from ${n.text}` : n.text, "hospital");
      if (n.kind === "alert" && voiceOn) speak(`Alert. ${n.text}`, "hospital");
    }
  }, [t, voiceOn]);

  const openQuestion: Note | null = useMemo(() => {
    if (!t) return null;
    const answered = new Set(t.notes.filter((n) => n.reply_to).map((n) => n.reply_to));
    return [...t.notes].reverse().find((n) => n.kind === "question" && !answered.has(n.id)) ?? null;
  }, [t]);

  const refresh = useCallback((next?: Transfer) => mutate(`/transfers/${transferId}`, next, { revalidate: !next }), [transferId]);

  // old links die when the demo is reset or the in-memory engine restarts — offer a way straight back in
  if (error && !t) {
    const startDemo = async () => {
      setStartingDemo(true);
      try {
        router.push(`/crew/${(await post<Transfer>("/demo/example")).id}`);
      } catch (err) {
        toastError(err);
        setStartingDemo(false);
      }
    };
    return (
      <div className="m-auto flex max-w-[26rem] flex-col items-center gap-[.5rem] text-center">
        <p className="text-[1.125rem] font-[600]">This transfer isn’t available.</p>
        <p className="text-[0.9375rem] text-ink-2">It may have been closed, or the demo was reset.</p>
        <div className="mt-[.75rem] flex gap-[.5rem]">
          <ButtonPrimary onClick={startDemo} disabled={startingDemo}>
            {startingDemo ? "Starting…" : "Start a demo case"}
          </ButtonPrimary>
          <Link href="/crew" className="inline-flex items-center rounded-[.75rem] px-[1rem] font-[600] text-accent hover:bg-accent-soft">
            All transfers
          </Link>
        </div>
      </div>
    );
  }
  if (!t || !meta) {
    return (
      <div className="flex flex-col gap-[1.5rem]">
        <Skeleton className="h-[4.5rem] w-[50%]" />
        <div className="grid gap-[1.5rem] md:grid-cols-[minmax(0,1.55fr)_minmax(21rem,1fr)]">
          <Skeleton className="aspect-[16/10] w-full rounded-[1.5rem]" />
          <Skeleton className="h-[26rem] rounded-[1.5rem]" />
        </div>
      </div>
    );
  }

  const dest = place(region, t.destination_id);
  const done = t.status === "arrived" || t.status === "closed";
  const conversation = t.notes.filter((n) => n.author !== "system");

  const act = async (path: "arrive" | "close") => {
    try {
      refresh(await post<Transfer>(`/transfers/${transferId}/${path}`));
    } catch (err) {
      toastError(err);
    }
  };

  return (
    <div className={styles.page}>
      {/* 1 · who, and where the transfer stands */}
      <header className={styles.header}>
        <div className={styles.who}>
          <div className="flex flex-wrap items-center gap-[.625rem]">
            <span className="font-mono text-[0.8125rem] font-[500] tracking-[0.02em] text-ink-3">{t.code}</span>
            <span id="handoff-target" className={twMerge("inline-flex rounded-full", justSent && styles.arrived)}>
              <StatusChip status={t.status} view="crew" />
            </span>
          </div>
          <h1 className={styles.title}>{patientTitle(t.patient)}</h1>
          <p className={styles.complaint} title={t.complaint}>
            {t.complaint}
          </p>
        </div>
        <div className={styles.headerEnd}>
          <RouteLine t={t} region={region} now={meta.now} align="right" className="max-md:items-start max-md:text-left" />
          <div className="flex gap-[.25rem] max-md:ml-[-0.75rem]">
            {t.pre_arrival && (
              <ButtonGhost size="sm" onClick={() => setSheet("packet")} title="What the companion sent ahead">
                <Smartphone size={16} /> Sent ahead
              </ButtonGhost>
            )}
            <ButtonGhost size="sm" onClick={() => setSheet("notes")}>
              <ListChecks size={16} /> Notes{conversation.length ? ` · ${conversation.length}` : ""}
            </ButtonGhost>
            <ButtonGhost
              size="sm"
              aria-pressed={voiceOn}
              title="Read hospital messages and alerts aloud"
              onClick={() => {
                if (voiceOn) stopSpeaking();
                setVoiceOn(!voiceOn);
              }}
            >
              {voiceOn ? <Volume2 size={16} /> : <VolumeX size={16} />} {voiceOn ? "Voice on" : "Muted"}
            </ButtonGhost>
          </div>
        </div>
      </header>

      {/* 2 + 3 · contactless assessment and vital signs */}
      {/* a phone always scans; a mounted tablet or laptop may stream continuously instead */}
      {active && !phone && (
        <div className={styles.modeRow}>
          <Segmented
            label="How contactless vitals are taken"
            size="sm"
            value={mode}
            onChange={setChosen}
            options={[
              { value: "scan", label: "Phone scan", title: "Presage measures for 30–60 s on a propped-up phone" },
              { value: "live", label: "Continuous", title: "Presage measures continuously from a mounted camera" },
            ]}
          />
        </div>
      )}
      <div className={styles.stage}>
        {mode === "scan" || !active ? (
          <ScanStage t={t} tz={region?.timezone} now={meta.now} onSaved={(next) => refresh(next)} />
        ) : (
          <CameraInstrument
            videoRef={videoRef}
            camera={cam.camera}
            instrument={instrument}
            hint={presage.hint}
            since={presage.since}
            rrStable={!!presage.metrics.rr?.stable}
            onRetry={cam.retry}
          />
        )}
        <VitalsPanel
          t={t}
          now={meta.now}
          live={live}
          acquiring={instrument.phase === "acquiring"}
          hr={live ? presage.metrics.hr : null}
          rr={live ? presage.metrics.rr : null}
          trace={presage.metrics.trace}
          onAddVitals={() => setSheet("vitals")}
        />
      </div>

      {/* 4 + 5 · note capture and the next step — the hospital's questions land on the mic itself */}
      <div className={twMerge(styles.dock, openQuestion && !done && styles.asking)}>
        <div className={styles.dockRow}>
          {!done ? (
            <VoiceCapture
              transferId={transferId}
              serverStt={meta.adapters.elevenlabs === "real"}
              question={openQuestion}
              askedBy={dest}
              onSaved={(next) => refresh(next)}
            />
          ) : (
            <p className="flex items-center gap-[.5rem] px-[.25rem] text-[1rem] font-[600]">
              <Check size={18} className="text-teal" /> Handed over at {dest}
            </p>
          )}
          <div className={styles.next}>
            {t.status === "preparing" && (
              <ButtonPrimary size="lg" onClick={() => setSheet("handoff")}>
                Send handoff <ArrowUpRight size={18} />
              </ButtonPrimary>
            )}
            {t.status === "pending" && (
              <>
                <span className={styles.waiting}>
                  <Clock3 size={16} /> <span className="max-sm:hidden">Waiting for {dest}</span>
                  <span className="sm:hidden">Waiting</span>
                </span>
                <ButtonBase onClick={() => setSheet("handoff")}>View handoff</ButtonBase>
              </>
            )}
            {t.status === "accepted" && t.acceptance && (
              <>
                <button type="button" className={styles.accepted} onClick={() => setSheet("notes")} title={t.acceptance.message ?? "Notes and messages"}>
                  <CheckCircle2 size={18} className="shrink-0" />
                  <span className="min-w-0 text-left">
                    <span className="block truncate font-[600]">Accepted · {t.acceptance.by}</span>
                    {/* the hospital's own words come first: they're what the crew acts on */}
                    <span className="block truncate text-[0.8125rem] opacity-80">
                      {t.acceptance.message
                        ? `“${t.acceptance.message}”`
                        : t.acceptance.prepare.length
                          ? `Preparing ${t.acceptance.prepare.join(", ").toLowerCase()}`
                          : "Receiving team ready"}
                    </span>
                  </span>
                </button>
                <ButtonBase size="lg" onClick={() => act("arrive")}>
                  <Flag size={18} /> Arrived
                </ButtonBase>
              </>
            )}
            {t.status === "arrived" && (
              <ButtonBase size="lg" onClick={() => act("close")}>
                Close transfer
              </ButtonBase>
            )}
          </div>
        </div>
      </div>

      <HandoffSheet
        t={t}
        region={region}
        now={meta.now}
        open={sheet === "handoff"}
        readOnly={t.status !== "preparing"}
        onClose={() => setSheet(null)}
        onChanged={(next) => refresh(next)}
        onSent={(next) => {
          setSheet(null);
          refresh(next);
          setJustSent(true);
          window.setTimeout(() => setJustSent(false), 1400);
          toast(`Handoff sent to ${dest}`);
        }}
      />
      <VitalsSheet transferId={transferId} open={sheet === "vitals"} onClose={() => setSheet(null)} onSaved={() => refresh()} />
      <Sheet open={sheet === "packet"} onClose={() => setSheet(null)} title="Sent ahead" subtitle={`${t.pre_arrival?.code ?? ""} · from the companion’s phone`}>
        <PreArrivalPanel t={{ ...t, scans: [] }} tz={region?.timezone} />
      </Sheet>
      <Sheet open={sheet === "notes"} onClose={() => setSheet(null)} title="Notes and messages" subtitle={`${t.code} · ${patientTitle(t.patient)}`}>
        <Timeline notes={t.notes} tz={region?.timezone} />
      </Sheet>
    </div>
  );
}
