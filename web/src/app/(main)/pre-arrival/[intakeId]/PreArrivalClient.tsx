// Pre-arrival on the companion's phone, one thing per screen: film (Presage measures live), say what happened, their
// ID, then review and send. Each step can be skipped; nothing reaches the health centre until Send. The bystander sees
// what was measured in plain numbers, never the engine's diagnostics; those are for the hospital.
"use client";

import { ArrowRight, Check, ChevronLeft, Loader2, RotateCcw, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import Segmented from "@/app/components/(controls)/Segmented";
import ScanRecorder from "@/app/components/(scan)/ScanRecorder";
import { Mark } from "@/app/components/(shell)/TopBar";
import { Heartbeat } from "@/app/components/(vitals)/Signal";
import Skeleton from "@/app/components/Skeleton";
import { patch, post, type Intake } from "@/lib/api";
import { patientTitle } from "@/lib/clinical";
import { place } from "@/lib/format";
import { useIntake, useMeta } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "../PreArrival.module.scss";
import AccountCapture from "./AccountCapture";
import IdCapture from "./IdCapture";

type Sex = "F" | "M" | "X";
type StepId = "film" | "account" | "id" | "review";
const ORDER: StepId[] = ["film", "account", "id", "review"];
type Scan = Intake["scans"][number];

// where to pick up: the first thing not done yet
function firstOpen(i: Intake): StepId {
  if (!i.scans.length) return "film";
  if (!i.account) return "account";
  if (!i.identity) return "id";
  return "review";
}

/** What the video measured, for the person who filmed it: two numbers, or one plain sentence. */
function VideoSummary({ scan }: { scan: Scan }) {
  const v = scan.vitals;
  const hr = v?.heart_rate_bpm ?? null;
  const rr = v?.respiration_rate_bpm ?? null;
  if (hr === null && rr === null) {
    return (
      <p className={styles.summaryLine}>
        {scan.status === "processing" ? (
          <>
            <Loader2 size={16} strokeWidth={1.75} className="animate-spin" /> Measuring your video
          </>
        ) : (
          "No steady reading from this video. The health centre still gets it."
        )}
      </p>
    );
  }
  return (
    <div className={styles.vitals}>
      <Heartbeat bpm={v?.heart_rate_stable ? hr : null} tone="card" size="md" />
      <p className={styles.vital}>
        <span className="numeral">{hr ?? "—"}</span>
        <span className="unit">bpm</span>
      </p>
      <p className={styles.vital}>
        <span className="numeral">{rr ?? "—"}</span>
        <span className="unit">breaths a minute</span>
      </p>
    </div>
  );
}

export default function ({ intakeId }: { intakeId: string }) {
  const { data: intake, error } = useIntake(intakeId);
  const { data: meta } = useMeta();
  const [step, setStep] = useState<StepId | null>(null);
  const [recordAgain, setRecordAgain] = useState(false);
  const [sending, setSending] = useState(false);
  const region = meta?.regions.find((r) => r.id === intake?.region_id);
  const refresh = (next: Intake) => mutate(`/intakes/${intakeId}`, next, { revalidate: false });

  if (error && !intake) {
    return (
      <div className={styles.page}>
        <h1 className={styles.title}>This packet isn&apos;t available</h1>
        <Link href="/pre-arrival" className={styles.quietLink}>
          Start a new one
        </Link>
      </div>
    );
  }
  if (!intake || !meta) {
    return (
      <div className={styles.page}>
        <Skeleton className="h-[2.5rem] w-[60%] rounded-full" />
        <Skeleton className="h-[34rem] rounded-[2.5rem]" />
      </div>
    );
  }

  const centre = intake.health_centre_id ? place(region, intake.health_centre_id) : null;
  const scan = intake.scans.at(-1);
  const sent = intake.status !== "draft";
  const ready = !!(intake.account || intake.scans.length || intake.identity);
  const current = step ?? firstOpen(intake);
  const index = ORDER.indexOf(current);
  const go = (s: StepId) => {
    setStep(s);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };
  const next = () => go(ORDER[Math.min(index + 1, ORDER.length - 1)]);

  const setPatient = async (update: { age?: number | null; sex?: Sex | null }) => {
    try {
      refresh(await patch<Intake>(`/intakes/${intakeId}`, { patient: { ...intake.patient, ...update } }));
    } catch (err) {
      toastError(err);
    }
  };

  const send = async () => {
    setSending(true);
    try {
      refresh(await post<Intake>(`/intakes/${intakeId}/send`));
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (err) {
      toastError(err);
    } finally {
      setSending(false);
    }
  };

  if (sent) {
    const items = [
      { label: "Video", done: !!scan, detail: scan?.vitals?.heart_rate_bpm ? `${scan.vitals.heart_rate_bpm} bpm` : scan ? "Sent" : "Not filmed" },
      { label: "What happened", done: !!intake.account, detail: intake.account ? "In your words" : "Not given" },
      { label: "ID", done: !!intake.identity, detail: intake.identity?.full_name ?? "Not given" },
    ];
    return (
      <div className={styles.page}>
        <section className={twMerge("card", styles.sent)}>
          <span className={styles.sentMark}>
            <Check size={22} strokeWidth={2} />
          </span>
          <h1 className={styles.title}>Sent to {centre ?? "the health centre"}</h1>
          <p className={styles.lede}>They can see it now. Show them this code when you arrive.</p>
          <p className={styles.code}>
            <span className="numeral">{intake.code}</span>
          </p>
        </section>
        <ul className={twMerge("card", styles.checklist)}>
          {items.map((it) => (
            <li key={it.label} className={twMerge(!it.done && styles.checkMissing)}>
              <span className={styles.checkMark}>{it.done ? <Check size={14} strokeWidth={2.25} /> : null}</span>
              <span className={styles.checkLabel}>{it.label}</span>
              <span className={styles.checkDetail}>{it.detail}</span>
            </li>
          ))}
        </ul>
        {scan?.status === "processing" && <p className={styles.note}>The video is still being checked; they&apos;ll see the result when it&apos;s ready.</p>}
        <Link href="/pre-arrival" className={styles.quietLink}>
          Start another
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={twMerge("glass", styles.wizardBar)}>
        {index === 0 ? (
          <span className={styles.wizardMark} aria-hidden>
            <Mark className="h-[1.125rem] w-[1.125rem]" />
          </span>
        ) : (
          <button type="button" className={styles.back} onClick={() => go(ORDER[index - 1])} aria-label="Back">
            <ChevronLeft size={20} strokeWidth={1.75} />
          </button>
        )}
        <span className={styles.wizardTo}>To {centre ?? "the health centre"}</span>
        <span className={styles.pips} aria-label={`Step ${index + 1} of ${ORDER.length}`}>
          {ORDER.map((s, i) => (
            <span key={s} className={twMerge(styles.pip, i < index && styles.pipDone, i === index && styles.pipNow)} />
          ))}
        </span>
      </header>

      {current === "film" && (
        <section className={twMerge(styles.step, styles.filmStep)} key="film">
          <h1 className={styles.stepTitle}>Film them for 30 seconds</h1>
          {!scan || recordAgain ? (
            <ScanRecorder<Intake>
              endpoint={`/intakes/${intakeId}/scans`}
              onSent={(nextIntake) => {
                refresh(nextIntake);
                setRecordAgain(false);
                go(nextIntake.account ? "id" : "account");
              }}
              withAudio
            />
          ) : (
            <div className={twMerge("card", styles.panel)}>
              <VideoSummary scan={scan} />
              <button type="button" className={styles.inlineAction} onClick={() => setRecordAgain(true)}>
                <RotateCcw size={16} strokeWidth={1.75} /> Film again
              </button>
            </div>
          )}
          <footer className={styles.stepNav}>
            {scan && !recordAgain ? (
              <ButtonPrimary size="lg" className="w-full" onClick={next}>
                Next <ArrowRight size={18} strokeWidth={1.75} />
              </ButtonPrimary>
            ) : (
              <button type="button" className={styles.quietLink} onClick={next}>
                Can&apos;t film? Skip this
              </button>
            )}
          </footer>
        </section>
      )}

      {current === "account" && (
        <section className={twMerge(styles.step, styles.fullStep)} key="account">
          <h1 className={styles.stepTitle}>What happened?</h1>
          <p className={styles.stepLede}>What you saw, and when it started.</p>
          {!intake.account && (
            <ul className={styles.prompts} aria-label="Things to mention">
              <li>When did it start?</li>
              <li>What did they say or do?</li>
              <li>Any medicines, drink or drugs?</li>
            </ul>
          )}
          <AccountCapture intake={intake} onSaved={refresh} />
          <footer className={styles.stepNav}>
            {intake.account ? (
              <ButtonPrimary size="lg" className="w-full" onClick={next}>
                Next <ArrowRight size={18} strokeWidth={1.75} />
              </ButtonPrimary>
            ) : (
              <button type="button" className={styles.quietLink} onClick={next}>
                Skip for now
              </button>
            )}
          </footer>
        </section>
      )}

      {current === "id" && (
        <section className={twMerge(styles.step, styles.fullStep)} key="id">
          <h1 className={styles.stepTitle}>Their ID</h1>
          <p className={styles.stepLede}>Optional. Only the name, ID number and age are read.</p>
          <IdCapture intake={intake} onSaved={refresh} />
          <footer className={styles.stepNav}>
            {intake.identity ? (
              <ButtonPrimary size="lg" className="w-full" onClick={next}>
                Next <ArrowRight size={18} strokeWidth={1.75} />
              </ButtonPrimary>
            ) : (
              <button type="button" className={styles.quietLink} onClick={next}>
                No ID? Skip this
              </button>
            )}
          </footer>
        </section>
      )}

      {current === "review" && (
        <section className={styles.step} key="review">
          <h1 className={styles.stepTitle}>Ready to send</h1>
          <div className={styles.reviewGrid}>
            <button type="button" className={twMerge("card", styles.reviewCard)} onClick={() => go("film")}>
              <span className={styles.reviewLabel}>Video</span>
              {scan ? <VideoSummary scan={scan} /> : <span className={styles.reviewEmpty}>Not filmed · add</span>}
            </button>
            <button type="button" className={twMerge("card", styles.reviewCard)} onClick={() => go("account")}>
              <span className={styles.reviewLabel}>What happened</span>
              {intake.account ? <span className={styles.reviewQuote}>“{intake.account}”</span> : <span className={styles.reviewEmpty}>Not given · add</span>}
            </button>
            <button type="button" className={twMerge("card", styles.reviewCard)} onClick={() => go("id")}>
              <span className={styles.reviewLabel}>ID</span>
              {intake.identity ? (
                <span className={styles.reviewValue}>
                  {intake.identity.full_name ?? "Read"}
                  {intake.identity.age != null && <span className={styles.reviewMeta}> · {intake.identity.age}</span>}
                </span>
              ) : (
                <span className={styles.reviewEmpty}>Not given · add</span>
              )}
            </button>
            <div className={twMerge("card", styles.reviewCard)}>
              <span className={styles.reviewLabel}>About the patient {intake.patient.age || intake.patient.sex ? `· ${patientTitle(intake.patient)}` : ""}</span>
              <div className={styles.patient}>
                <label className={field.field}>
                  <span className="sr-only">Age</span>
                  <input
                    className={field.input}
                    inputMode="numeric"
                    defaultValue={intake.patient.age ?? ""}
                    key={intake.patient.age ?? "none"}
                    onBlur={(e) => {
                      const n = parseInt(e.target.value, 10);
                      const age = Number.isFinite(n) && n >= 0 && n < 130 ? n : null;
                      if (age !== (intake.patient.age ?? null)) setPatient({ age });
                    }}
                    placeholder="Age"
                    aria-label="Age"
                  />
                </label>
                <Segmented
                  label="Sex"
                  className="w-full"
                  value={(intake.patient.sex as Sex | null) ?? null}
                  onChange={(sex) => setPatient({ sex })}
                  options={[
                    { value: "F", label: "Female" },
                    { value: "M", label: "Male" },
                    { value: "X", label: "Other" },
                  ]}
                />
              </div>
            </div>
          </div>

          <div className={twMerge("glass", styles.sendDock)}>
            <p className={styles.sendText}>{ready ? `${centre ?? "The health centre"} sees nothing until you send.` : "Add the video, what happened or the ID first."}</p>
            <ButtonPrimary size="lg" onClick={send} disabled={!ready || sending}>
              {sending ? <Loader2 size={18} strokeWidth={1.75} className="animate-spin" /> : <Send size={18} strokeWidth={1.75} />} Send
            </ButtonPrimary>
          </div>
        </section>
      )}
    </div>
  );
}
