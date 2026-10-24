// Crew: start a transfer (who, what happened, from, to, how) or resume an active one.
"use client";

import { Loader2, Mic, Play, Square } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import ModeIcon from "@/app/components/(transfer)/ModeIcon";
import StatusPill from "@/app/components/(transfer)/StatusPill";
import Card from "@/app/components/Card";
import { post, type Transfer, type TransportMode } from "@/lib/api";
import { useDictation } from "@/lib/dictation";
import { fmtTime, MODE_LABEL, patientLine, place } from "@/lib/format";
import { useMeta, useTransfers } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./Crew.module.scss";

export default function () {
  const router = useRouter();
  const { data: meta } = useMeta();
  const { data: active } = useTransfers("pending,accepted");
  const region = meta?.region;
  const [age, setAge] = useState("");
  const [sex, setSex] = useState<"M" | "F" | "X" | "">("");
  const [complaint, setComplaint] = useState("");
  const [origin, setOrigin] = useState("");
  const [dest, setDest] = useState("");
  const [mode, setMode] = useState<TransportMode | "">("");
  const [busy, setBusy] = useState<"start" | "example" | null>(null);

  const dictation = useDictation(false, (r) => r.kind === "text" && setComplaint((c) => (c ? `${c} ${r.text}` : r.text)));
  const hospitals = useMemo(() => region?.facilities.filter((f) => f.kind === "hospital") ?? [], [region]);
  const origins = region?.facilities ?? [];
  const chosenMode = mode || region?.modes[0] || "";
  const chosenDest = dest || hospitals[0]?.id || "";
  const chosenOrigin = origin || origins.find((f) => f.kind === "clinic")?.id || "";
  const ready = complaint.trim() && chosenOrigin && chosenDest && chosenOrigin !== chosenDest && chosenMode;

  const start = async () => {
    setBusy("start");
    try {
      const t = await post<Transfer>("/transfers", {
        patient: { age: age ? Number(age) : null, sex: sex || null },
        complaint,
        origin_id: chosenOrigin,
        destination_id: chosenDest,
        mode: chosenMode,
      });
      router.push(`/crew/${t.id}`);
    } catch (err) {
      toastError(err);
      setBusy(null);
    }
  };

  const example = async () => {
    setBusy("example");
    try {
      const t = await post<Transfer>("/demo/example");
      router.push(`/crew/${t.id}`);
    } catch (err) {
      toastError(err);
      setBusy(null);
    }
  };

  return (
    <div className="mx-auto grid max-w-[72rem] gap-[1.25rem] lg:grid-cols-[1fr_22rem]">
      <Card>
        <h1 className="text-[1.5rem] font-bold">Start a transfer</h1>
        <p className="mb-[1.25rem] text-muted">The hospital sees the patient as soon as you start.</p>
        <div className="flex flex-col gap-[1.25rem]">
          <div className="grid grid-cols-[8rem_1fr] gap-[.75rem]">
            <label className={styles.field}>
              <span>Age</span>
              <input type="number" inputMode="numeric" min={0} max={120} value={age} onChange={(e) => setAge(e.target.value)} />
            </label>
            <div className={styles.field}>
              <span>Sex</span>
              <div className={styles.segmented}>
                {(["F", "M", "X"] as const).map((s) => (
                  <button key={s} type="button" aria-pressed={sex === s} onClick={() => setSex(sex === s ? "" : s)}>
                    {s === "F" ? "Female" : s === "M" ? "Male" : "Other"}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <label className={styles.field}>
            <span>What happened?</span>
            <textarea
              value={complaint}
              onChange={(e) => setComplaint(e.target.value)}
              placeholder="e.g. Crushing chest pain for 40 minutes, sweating"
            />
          </label>
          {dictation.supported && (
            <div className="-mt-[.75rem] flex items-center gap-[.75rem]">
              <button type="button" onClick={dictation.toggle} className={styles.inlineMic} aria-pressed={dictation.state === "listening"}>
                {dictation.state === "listening" ? <Square size={16} /> : <Mic size={16} />}
                {dictation.state === "listening" ? "Stop" : "Dictate"}
              </button>
              <span className="truncate text-[0.875rem] text-muted">{dictation.state === "listening" ? dictation.transcript || "Listening…" : dictation.error}</span>
            </div>
          )}

          <div className="grid gap-[.75rem] sm:grid-cols-2">
            <label className={styles.field}>
              <span>From</span>
              <select value={chosenOrigin} onChange={(e) => setOrigin(e.target.value)}>
                {origins.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.short_name}
                  </option>
                ))}
              </select>
            </label>
            <label className={styles.field}>
              <span>To</span>
              <select value={chosenDest} onChange={(e) => setDest(e.target.value)}>
                {hospitals.map((f) => (
                  <option key={f.id} value={f.id}>
                    {f.short_name}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className={styles.field}>
            <span>Transport</span>
            <div className={styles.segmented}>
              {(region?.modes ?? []).map((m) => (
                <button key={m} type="button" aria-pressed={chosenMode === m} onClick={() => setMode(m)}>
                  <ModeIcon mode={m} /> {MODE_LABEL[m]}
                </button>
              ))}
            </div>
          </div>

          <ButtonPrimary className="min-h-[3.25rem] text-[1.0625rem]" disabled={!ready || busy !== null} onClick={start}>
            {busy === "start" ? <Loader2 size={20} className="animate-spin" /> : <Play size={20} />}
            Start transfer
          </ButtonPrimary>
        </div>
      </Card>

      <div className="flex flex-col gap-[1rem]">
        <Card title="Active transfers">
          {!active?.length && <p className="text-muted">None right now.</p>}
          <ul className="flex flex-col gap-[.5rem]">
            {active?.map((t) => (
              <li key={t.id}>
                <Link href={`/crew/${t.id}`} className={styles.resume}>
                  <span className="flex items-center justify-between gap-[.5rem]">
                    <strong className="tabular-nums">{t.code}</strong>
                    <StatusPill status={t.status} />
                  </span>
                  <span className="text-[0.875rem] text-muted">
                    {patientLine(t.patient)} · {place(meta?.regions.find((r) => r.id === t.region_id), t.origin_id)} →{" "}
                    {place(meta?.regions.find((r) => r.id === t.region_id), t.destination_id)} · ETA{" "}
                    {fmtTime(t.eta, meta?.regions.find((r) => r.id === t.region_id)?.timezone)}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
        <Card title="Demo">
          <p className="mb-[.75rem] text-[0.875rem] text-muted">
            Starts the {region?.name ?? "region"} example patient with 8 minutes of history already recorded.
          </p>
          <ButtonBase className={twMerge("w-full")} onClick={example} disabled={busy !== null}>
            {busy === "example" ? <Loader2 size={18} className="animate-spin" /> : null}
            Load example patient
          </ButtonBase>
        </Card>
      </div>
    </div>
  );
}
