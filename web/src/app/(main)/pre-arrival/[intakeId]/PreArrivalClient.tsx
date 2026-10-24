// Pre-arrival on the companion's phone: three steps, one packet. Results fill in as they land (Gemini's sign check
// in seconds, Presage's heart and breathing rate in about a minute), and nothing reaches the health centre until Send.
"use client";

import { Check, CheckCircle2, Loader2, Send } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import Segmented from "@/app/components/(controls)/Segmented";
import ScanRecorder from "@/app/components/(scan)/ScanRecorder";
import ScanResult from "@/app/components/(scan)/ScanResult";
import Skeleton from "@/app/components/Skeleton";
import { api, patch, post, type Intake } from "@/lib/api";
import { place } from "@/lib/format";
import { useIntake, useMeta } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "../PreArrival.module.scss";
import AccountCapture from "./AccountCapture";
import IdCapture from "./IdCapture";

type Sex = "F" | "M" | "X";

function Step({ n, title, done, children, hint }: { n: number; title: string; done: boolean; hint?: string; children: React.ReactNode }) {
  return (
    <section className={styles.step}>
      <header className={styles.stepHead}>
        <span className={twMerge(styles.stepNo, done && styles.stepDone)}>{done ? <Check size={15} strokeWidth={3} /> : n}</span>
        <div className="min-w-0">
          <h2 className={styles.stepTitle}>{title}</h2>
          {hint && <p className={styles.stepHint}>{hint}</p>}
        </div>
      </header>
      {children}
    </section>
  );
}

export default function ({ intakeId }: { intakeId: string }) {
  const { data: intake, error } = useIntake(intakeId);
  const { data: meta } = useMeta();
  const [recordAgain, setRecordAgain] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const region = meta?.regions.find((r) => r.id === intake?.region_id);
  const refresh = (next: Intake) => mutate(`/intakes/${intakeId}`, next, { revalidate: false });

  if (error && !intake) {
    return (
      <div className={styles.page}>
        <p className="text-[1.125rem] font-[600]">This packet isn&apos;t available.</p>
        <Link href="/pre-arrival" className="font-[600] text-accent">
          Start a new one
        </Link>
      </div>
    );
  }
  if (!intake || !meta) {
    return (
      <div className={styles.page}>
        <Skeleton className="h-[3rem] w-[70%]" />
        <Skeleton className="h-[24rem] rounded-[1.5rem]" />
      </div>
    );
  }

  const centre = intake.health_centre_id ? place(region, intake.health_centre_id) : null;
  const scan = intake.scans.at(-1);
  const sent = intake.status !== "draft";
  const ready = !!(intake.account || intake.scans.length || intake.identity);

  const uploadClip = async (clip: Blob, filename: string) => {
    setUploading(true);
    const form = new FormData();
    form.append("video", clip, filename);
    try {
      refresh(await api<Intake>(`/intakes/${intakeId}/scans`, { method: "POST", body: form }));
      setRecordAgain(false);
    } catch (err) {
      toastError(err);
    } finally {
      setUploading(false);
    }
  };

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
    return (
      <div className={styles.page}>
        <section className={styles.sent}>
          <CheckCircle2 size={36} className="text-teal" />
          <h1 className={styles.title}>Sent to {centre ?? "the health centre"}</h1>
          <p className={styles.lede}>
            They can see it now. Show them this code when you arrive: <strong className="tnum">{intake.code}</strong>
          </p>
          {scan?.status === "processing" && <p className={styles.fine}>The video is still being measured; they&apos;ll see the result when it&apos;s ready.</p>}
        </section>
        {scan && (
          <section className={styles.card}>
            <ScanResult scan={scan} tz={region?.timezone} title="Your video" />
          </section>
        )}
        <Link href="/pre-arrival" className="self-center font-[600] text-accent">
          Start another
        </Link>
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <header className={styles.intro}>
        <p className={styles.eyebrow}>
          {intake.code} · going to {centre ?? "the health centre"}
        </p>
        <h1 className={styles.title}>Before you arrive</h1>
      </header>

      <Step n={1} title="Record the patient" done={!!scan} hint={scan ? undefined : "About 60 seconds. Heart and breathing rate are measured from the video."}>
        {!scan || recordAgain ? (
          <>
            <ScanRecorder onClip={uploadClip} disabled={uploading} />
            {uploading && (
              <p className={styles.uploading}>
                <Loader2 size={16} className="animate-spin" /> Sending the video…
              </p>
            )}
          </>
        ) : (
          <div className={styles.card}>
            <ScanResult scan={scan} tz={region?.timezone} title="Your video" />
            <button type="button" className={styles.link} onClick={() => setRecordAgain(true)}>
              Record again
            </button>
          </div>
        )}
      </Step>

      <Step n={2} title="What happened?" done={!!intake.account}>
        <AccountCapture intake={intake} onSaved={refresh} />
      </Step>

      <Step n={3} title="Their ID (optional)" done={!!intake.identity} hint="A driving licence or ID card. Only name, ID number and age are read.">
        <IdCapture intake={intake} onSaved={refresh} />
      </Step>

      <section className={styles.step}>
        <h2 className={styles.stepTitle}>About the patient</h2>
        <div className={styles.patient}>
          <label className={field.field}>
            <span className={field.label}>Age</span>
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
              placeholder="—"
            />
          </label>
          <div className={field.field}>
            <span className={field.label}>Sex</span>
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
      </section>

      <div className={styles.sendBar}>
        <p className={styles.sendText}>
          {ready ? `${centre ?? "The health centre"} sees nothing until you send.` : "Add the video, what happened, or the ID first."}
        </p>
        <ButtonPrimary size="lg" onClick={send} disabled={!ready || sending}>
          {sending ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />} Send
        </ButtonPrimary>
      </div>
    </div>
  );
}
