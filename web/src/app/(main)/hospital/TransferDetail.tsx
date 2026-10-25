// The arriving patient: identity and urgency, arrival, the decision, measurements with provenance, then the handoff
// and — when a phone sent it ahead or the crew scanned — the video, the companion's words and the ID.
"use client";

import { Check, CheckCircle2, Eye, MessageCircleQuestion, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import Segmented from "@/app/components/(controls)/Segmented";
import PreArrivalPanel from "@/app/components/(scan)/PreArrivalPanel";
import SbarDocument from "@/app/components/(transfer)/SbarDocument";
import StatusChip from "@/app/components/(transfer)/StatusChip";
import Timeline from "@/app/components/(transfer)/Timeline";
import TransferMapLazy from "@/app/components/(transfer)/TransferMapLazy";
import TrendChart from "@/app/components/(transfer)/TrendChart";
import UrgencyBadge from "@/app/components/(transfer)/UrgencyBadge";
import Skeleton from "@/app/components/Skeleton";
import { post, type CueFinding, type LatestValue, type Scan, type Transfer } from "@/lib/api";
import {
  assessHr,
  assessRr,
  assessSbp,
  assessSpo2,
  assessTemp,
  freshness,
  numeric,
  patientTitle,
  SOURCE_LABEL,
  type Assessment,
  type Source,
} from "@/lib/clinical";
import { fmtMin, fmtTime, MODE_LABEL, minutesUntil, place } from "@/lib/format";
import { useMeta, useTransfer, useTrend } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import AcceptModal from "./AcceptModal";
import ContactlessTile from "./ContactlessTile";
import styles from "./Hospital.module.scss";

const VITALS: { k: string; label: string; unit: string; a: (v: number) => Assessment }[] = [
  { k: "heart_rate", label: "Heart rate", unit: "bpm", a: assessHr },
  { k: "resp_rate", label: "Respiration", unit: "/min", a: assessRr },
  { k: "spo2", label: "SpO₂", unit: "%", a: assessSpo2 },
  { k: "systolic_bp", label: "Blood pressure", unit: "sys", a: assessSbp },
  { k: "temperature_c", label: "Temperature", unit: "°C", a: assessTemp },
];

const SUGGESTIONS = ["Any allergies?", "On blood thinners?", "Time of onset?", "Current pain score?"];

function Vital({ label, unit, lv, assess, now }: { label: string; unit: string; lv?: LatestValue; assess: (v: number) => Assessment; now: string }) {
  const v = numeric(lv);
  const simulated = lv?.source === "simulated";
  const a = v !== null && !simulated ? assess(v) : null; // no clinical status for a number nobody measured
  return (
    <div className={styles.vital}>
      <span className={styles.vitalHead}>
        <span className={styles.vitalLabel}>{label}</span>
        {a && a.level !== "normal" && <strong className={twMerge(styles.vitalWord, styles[a.level])}>{a.word}</strong>}
      </span>
      <span className={twMerge("tnum", styles.vitalValue, a && styles[a.level], simulated && styles.simulated)}>
        {v ?? "—"}
        {v !== null && <span className={styles.vitalUnit}>{unit}</span>}
      </span>
      <span className={styles.vitalMeta}>
        {lv ? (
          lv.source === "simulated" ? (
            <span className={styles.demoTag}>Simulated</span>
          ) : (
            `${SOURCE_LABEL[lv.source as Source]} · ${freshness(lv.at, now)}`
          )
        ) : (
          "Not recorded"
        )}
      </span>
      {lv?.flag && <span className={styles.vitalFlag}>Confirm — outside sensor range</span>}
    </div>
  );
}

// every sign Gemini saw on any video, with the frame it rests on: the one thing a receiving team can't get from numbers
function SeenOnVideo({ t, onOpen }: { t: Transfer; onOpen: () => void }) {
  const scans: { scan: Scan; who: string }[] = [
    ...(t.pre_arrival?.scans ?? []).map((scan) => ({ scan, who: "Companion’s video" })),
    ...t.scans.map((scan, i) => ({ scan, who: `Crew scan ${i + 1}` })),
  ];
  const seen = scans.flatMap(({ scan, who }) =>
    (scan.signs?.findings ?? []).filter((f) => f.finding === "present").map((f: CueFinding) => ({ f, scan, who })),
  );
  if (!scans.length) return null;
  const checking = scans.some(({ scan }) => scan.status === "processing");
  const checked = scans.some(({ scan }) => scan.signs?.findings.some((f) => f.finding === "absent"));
  return (
    <section className={styles.surface}>
      <h3 className={styles.sectionTitle}>Seen on video</h3>
      {seen.length ? (
        <ul className={styles.seen}>
          {seen.map(({ f, scan, who }) => {
            const frame = f.evidence_frames.find((i) => scan.evidence[String(i)]);
            return (
              <li key={`${scan.id}-${f.cue_id}`}>
                <button type="button" onClick={onOpen} className={styles.seenRow}>
                  {frame != null ? <img src={scan.evidence[String(frame)]} alt="" className={styles.seenThumb} /> : <Eye size={18} className="shrink-0 text-ink-3" />}
                  <span className="min-w-0">
                    <span className="block font-[600]">{f.label}</span>
                    <span className="block text-[0.8125rem] text-ink-3">
                      {who} · seen in {f.evidence_frames.length} of {scan.signs?.frames.length ?? 0} frames
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="text-[0.9375rem] text-ink-2">
          {checking ? "Checking the video…" : checked ? "No checklist signs were seen." : "The video didn’t show enough to check for signs."}{" "}
          <button type="button" onClick={onOpen} className="font-[600] text-accent">
            Details
          </button>
        </p>
      )}
    </section>
  );
}

export default function ({ transferId }: { transferId: string }) {
  const { data: t, error } = useTransfer(transferId);
  const { data: meta } = useMeta();
  const [tab, setTab] = useState<"handoff" | "video" | "trend" | "timeline" | "transport">("handoff");
  const { data: trend } = useTrend(tab === "trend" ? transferId : undefined);
  const [accepting, setAccepting] = useState(false);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);

  if (error && !t) {
    return (
      <div className={styles.missing}>
        <p className="text-[1.0625rem] font-[600]">This transfer isn’t available.</p>
        <p className="text-[0.9375rem] text-ink-2">It may have been closed, or the demo was reset.</p>
        <Link href="/hospital" className="mt-[.5rem] font-[600] text-accent">
          Show incoming transfers
        </Link>
      </div>
    );
  }
  if (!t || !meta) {
    return (
      <div className="flex flex-col gap-[1.25rem]">
        <Skeleton className="h-[7rem] rounded-[1.25rem]" />
        <Skeleton className="h-[6rem] rounded-[1.25rem]" />
        <Skeleton className="h-[20rem] rounded-[1.25rem]" />
      </div>
    );
  }

  const region = meta.regions.find((r) => r.id === t.region_id);
  const tz = region?.timezone;
  const dest = place(region, t.destination_id);
  const left = minutesUntil(t.eta, meta.now);
  const arrived = t.status === "arrived" || t.status === "closed";
  const answers = new Map(t.notes.filter((n) => n.reply_to).map((n) => [n.reply_to, n]));
  const questions = t.notes.filter((n) => n.kind === "question");
  const crewNotes = t.notes.filter((n) => n.author === "crew" && (n.kind === "voice" || n.kind === "text")).slice(-3).reverse();
  const refresh = (next: Transfer) => {
    mutate(`/transfers/${transferId}`, next, { revalidate: false });
    mutate((k) => typeof k === "string" && k.startsWith("/transfers?"));
  };

  const ask = async (text: string) => {
    if (!text.trim()) return;
    setAsking(true);
    let sender: string | null = null;
    try {
      sender = localStorage.getItem("atollcare.clinician");
    } catch {
      sender = null;
    }
    try {
      refresh(await post<Transfer>(`/transfers/${t.id}/messages`, { text: text.trim(), kind: "question", sender }));
      setQuestion("");
    } catch (err) {
      toastError(err);
    } finally {
      setAsking(false);
    }
  };

  return (
    <div className={styles.detail}>
      {/* who, how urgent, when — and the decision */}
      <header className={styles.hero}>
        <div className="min-w-0">
          <p className={styles.eyebrow}>
            <span className="font-mono">{t.code}</span> · {MODE_LABEL[t.mode]} from {place(region, t.origin_id)}
          </p>
          <h2 className={styles.heroTitle}>{t.briefing?.suspected_condition ?? t.complaint}</h2>
          <p className={styles.heroPatient}>
            {patientTitle(t.patient)}
            {t.pre_arrival?.identity?.full_name && (
              <span className="text-ink-2">
                {" · "}
                {t.pre_arrival.identity.full_name}
                {t.pre_arrival.identity.needs_review && <span className="text-[0.875rem] text-caution"> (from ID photo, check by eye)</span>}
              </span>
            )}
          </p>
          {t.briefing?.suspected_condition && (
            // a working impression, not a diagnosis — say where it came from and show the crew's own words
            <p className={styles.impression}>
              {t.briefing.generated_by === "gemini" ? "Impression suggested by Gemini from" : "Impression matched from"}{" "}
              {t.pre_arrival?.account ? "the companion’s account" : "the crew’s words"}:{" "}
              <q className="text-ink">{t.complaint}</q>
            </p>
          )}
          <div className="mt-[.875rem] flex flex-wrap items-center gap-[.5rem]">
            <UrgencyBadge news2={t.news2} size="lg" />
            <StatusChip status={t.status} view="hospital" />
          </div>
          {t.alerts.length > 0 && (
            <p className={twMerge(styles.alertLine, t.alerts.some((a) => a.level === "critical") ? "text-critical" : "text-caution")}>
              {t.alerts.map((a) => a.text).join(" · ")}
            </p>
          )}
        </div>

        <div className={styles.decision}>
          <p className={styles.arrivalLabel}>{arrived ? "Arrived" : "Arriving"}</p>
          <p className={twMerge("tnum", styles.arrivalTime)}>{fmtTime(arrived ? t.arrived_at : t.eta, tz)}</p>
          {!arrived && left !== null && <p className="tnum text-[0.9375rem] text-ink-2">in {fmtMin(left)} · {dest}</p>}
          <div className={styles.progress}>
            <span style={{ transform: `scaleX(${t.progress})` }} />
          </div>
          {t.status === "pending" && (
            <ButtonPrimary size="lg" className={styles.accept} onClick={() => setAccepting(true)}>
              <Check size={18} /> Accept transfer
            </ButtonPrimary>
          )}
          {t.acceptance && (
            <p className={styles.accepted}>
              <CheckCircle2 size={18} className="shrink-0" />
              <span>
                Accepted by {t.acceptance.by}
                {t.acceptance.prepare.length ? ` · ${t.acceptance.prepare.join(", ")}` : ""}
              </span>
            </p>
          )}
        </div>
      </header>

      {/* Presage: what the camera measured, and how long before arrival the team knew */}
      <ContactlessTile t={t} tz={tz} now={meta.now} />

      {/* measurements, with provenance */}
      <div className={styles.vitals}>
        {VITALS.map((v) => (
          <Vital key={v.k} label={v.label} unit={v.unit} lv={t.latest[v.k]} assess={v.a} now={meta.now} />
        ))}
        <div className={styles.vital}>
          <span className={styles.vitalLabel}>Consciousness</span>
          <span className={twMerge(styles.vitalValue, t.latest.consciousness && t.latest.consciousness.value !== "A" && styles.urgent)}>
            {t.latest.consciousness ? String(t.latest.consciousness.value) : "—"}
          </span>
          <span className={styles.vitalMeta}>{t.latest.consciousness ? `ACVPU · ${freshness(t.latest.consciousness.at, meta.now)}` : "Not recorded"}</span>
        </div>
      </div>

      {/* progressive disclosure */}
      <Segmented
        label="Section"
        size="sm"
        value={tab}
        onChange={setTab}
        className="self-start"
        options={[
          { value: "handoff", label: "Handoff" },
          ...(t.pre_arrival || t.scans.length ? [{ value: "video" as const, label: t.pre_arrival?.identity ? "Video & ID" : "Video" }] : []),
          { value: "trend", label: "Trend" },
          { value: "timeline", label: "Timeline" },
          { value: "transport", label: "Transport" },
        ]}
      />

      {tab === "handoff" && (
        <div className={twMerge(styles.columns, "fade-in")}>
          <div className={styles.surface}>
            <SbarDocument briefing={t.briefing} interventions={t.interventions} now={meta.now} tz={tz} />
          </div>
          <div className="flex min-w-0 flex-col gap-[1.25rem]">
            <SeenOnVideo t={t} onOpen={() => setTab("video")} />
            <section className={styles.surface}>
              <h3 className={styles.sectionTitle}>Ask the crew</h3>
              {!arrived && (
                <form
                  className={styles.askForm}
                  onSubmit={(e) => {
                    e.preventDefault();
                    ask(question);
                  }}
                >
                  <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Read aloud in the vehicle" aria-label="Question for the crew" />
                  <button type="submit" disabled={asking || !question.trim()} aria-label="Send question">
                    <Send size={16} />
                  </button>
                </form>
              )}
              {!arrived && (
                <div className="mt-[.625rem] flex flex-wrap gap-[.375rem]">
                  {SUGGESTIONS.map((s) => (
                    <button key={s} type="button" disabled={asking} onClick={() => ask(s)} className={styles.suggestion}>
                      {s}
                    </button>
                  ))}
                </div>
              )}
              {questions.length > 0 && (
                <ul className="mt-[1rem] flex flex-col gap-[.875rem] border-t-[1px] border-line pt-[1rem]">
                  {[...questions].reverse().map((q) => {
                    const a = answers.get(q.id);
                    return (
                      <li key={q.id}>
                        <p className="flex items-start gap-[.5rem] text-[0.9375rem] text-ink-2">
                          <MessageCircleQuestion size={16} className="mt-[.1875rem] shrink-0 text-accent" />
                          {q.text.split(": ").slice(1).join(": ") || q.text}
                        </p>
                        <p className={twMerge("ml-[1.5rem] mt-[.125rem] text-[0.9375rem]", a ? "rise-in font-[550] text-ink" : "text-ink-3")}>
                          {a ? a.text : "Waiting for the crew…"}
                        </p>
                      </li>
                    );
                  })}
                </ul>
              )}
            </section>
            {crewNotes.length > 0 && (
              <section className={styles.surface}>
                <h3 className={styles.sectionTitle}>Latest from the crew</h3>
                <Timeline notes={crewNotes} tz={tz} newestFirst={false} />
              </section>
            )}
          </div>
        </div>
      )}
      {tab === "video" && (
        <div className={twMerge(styles.surface, "fade-in")}>
          <PreArrivalPanel t={t} tz={tz} />
        </div>
      )}
      {tab === "trend" && (
        <div className={twMerge(styles.surface, "fade-in")}>
          <TrendChart trend={trend} tz={tz} />
        </div>
      )}
      {tab === "timeline" && (
        <div className={twMerge(styles.surface, "fade-in")}>
          <Timeline notes={t.notes} tz={tz} />
        </div>
      )}
      {tab === "transport" && (
        <div className={twMerge(styles.columns, "fade-in")}>
          <TransferMapLazy t={t} region={region} height="22rem" />
          <dl className={twMerge(styles.surface, styles.facts)}>
            <div><dt>From</dt><dd>{place(region, t.origin_id)}</dd></div>
            <div><dt>To</dt><dd>{dest}</dd></div>
            <div><dt>Transport</dt><dd>{MODE_LABEL[t.mode]}</dd></div>
            <div><dt>Distance</dt><dd className="tnum">{Math.round(t.distance_km)} km</dd></div>
            <div><dt>Departed</dt><dd className="tnum">{fmtTime(t.departed_at, tz)}</dd></div>
            <div><dt>{arrived ? "Arrived" : "ETA"}</dt><dd className="tnum">{fmtTime(arrived ? t.arrived_at : t.eta, tz)}</dd></div>
          </dl>
        </div>
      )}

      <AcceptModal t={t} open={accepting} onClose={() => setAccepting(false)} options={meta.prepare_options} onDone={refresh} />
      {t.status === "pending" && (
        <div className={styles.mobileDecision}>
          <ButtonBase onClick={() => setTab("handoff")}>Ask crew</ButtonBase>
          <ButtonPrimary className="flex-1" onClick={() => setAccepting(true)}>
            <Check size={18} /> Accept transfer
          </ButtonPrimary>
        </div>
      )}
    </div>
  );
}
