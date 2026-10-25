// Crew home: continue an active transfer, pick up a packet a companion sent ahead, or start one from scratch.
"use client";

import { ArrowRight, Loader2, Mic, Square } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import Segmented from "@/app/components/(controls)/Segmented";
import ModeIcon from "@/app/components/(transfer)/ModeIcon";
import { post, type Transfer, type TransportMode } from "@/lib/api";
import { patientTitle } from "@/lib/clinical";
import { useDictation } from "@/lib/dictation";
import { fmtMin, MODE_LABEL, minutesUntil, place } from "@/lib/format";
import { useIntakes, useMeta, useTransfers } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import SentAhead from "./SentAhead";
import styles from "./Start.module.scss";

type Sex = "F" | "M" | "X";

export default function () {
  const router = useRouter();
  const { data: meta } = useMeta();
  const { data: active } = useTransfers("preparing,pending,accepted");
  const { data: sent } = useIntakes("sent");
  const region = meta?.region;
  const [age, setAge] = useState("");
  const [sex, setSex] = useState<Sex | null>(null);
  const [complaint, setComplaint] = useState("");
  const [origin, setOrigin] = useState("");
  const [dest, setDest] = useState("");
  const [mode, setMode] = useState<TransportMode | "">("");
  const [busy, setBusy] = useState(false);

  const dictation = useDictation(false, (r) => r.kind === "text" && setComplaint((c) => (c ? `${c} ${r.text}` : r.text)));
  const hospitals = useMemo(() => region?.facilities.filter((f) => f.kind === "hospital") ?? [], [region]);
  const origins = region?.facilities ?? [];
  const chosenMode = mode || region?.modes[0] || "";
  const chosenDest = dest || hospitals[0]?.id || "";
  const chosenOrigin = origin || origins.find((f) => f.kind === "clinic")?.id || "";
  const ready = complaint.trim() && chosenOrigin && chosenDest && chosenOrigin !== chosenDest && chosenMode;

  const start = async () => {
    setBusy(true);
    try {
      const t = await post<Transfer>("/transfers", {
        patient: { age: age ? Number(age) : null, sex },
        complaint,
        origin_id: chosenOrigin,
        destination_id: chosenDest,
        mode: chosenMode,
      });
      router.push(`/crew/${t.id}`);
    } catch (err) {
      toastError(err);
      setBusy(false);
    }
  };

  return (
    <div className={styles.page}>
      {!!active?.length && (
        <section className="rise-in">
          <h2 className={styles.eyebrow}>In progress</h2>
          <ul className={styles.list}>
            {active.map((t) => {
              const r = meta?.regions.find((x) => x.id === t.region_id);
              const left = minutesUntil(t.eta, meta?.now);
              return (
                <li key={t.id}>
                  <Link href={`/crew/${t.id}`} className={styles.row}>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-[.625rem]">
                        <span className="font-[500]">{patientTitle(t.patient)}</span>
                        <span className="mono text-[0.8125rem] text-ink-3">{t.code}</span>
                      </span>
                      <span className="block truncate text-[0.875rem] text-ink-3">{t.suspected_condition ?? t.complaint}</span>
                      <span className="block truncate text-[0.8125rem] text-ink-3">
                        {place(r, t.origin_id)} → {place(r, t.destination_id)}
                      </span>
                    </span>
                    {left !== null && (
                      <span className={styles.rowEta} title={`ETA ${fmtMin(left)}`}>
                        {left >= 60 ? (
                          <>
                            <span className="numeral">{Math.floor(Math.round(left) / 60)}</span>
                            <span className="unit">h</span>
                            <span className="numeral">{String(Math.round(left) % 60).padStart(2, "0")}</span>
                          </>
                        ) : (
                          <>
                            <span className="numeral">{Math.max(0, Math.round(left))}</span>
                            <span className="unit">min</span>
                          </>
                        )}
                      </span>
                    )}
                  </Link>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {!!sent?.length && meta && <SentAhead intakes={sent} meta={meta} />}

      <section className={styles.composer}>
        <header>
          <h1 className={styles.title}>New transfer</h1>
          <p className={styles.lede}>Start here. You can add vitals and notes once you’re moving.</p>
        </header>

        <label className={field.field}>
          <span className={field.label}>What’s happening</span>
          <div className="relative">
            <textarea
              className={`${field.textarea} pr-[3.5rem]`}
              value={complaint}
              onChange={(e) => setComplaint(e.target.value)}
              placeholder="Crushing chest pain for 40 minutes, sweating…"
            />
            {dictation.supported && (
              <button
                type="button"
                onClick={dictation.toggle}
                aria-pressed={dictation.state === "listening"}
                aria-label={dictation.state === "listening" ? "Stop dictation" : "Dictate"}
                className={styles.dictate}
              >
                {dictation.state === "listening" ? <Square size={14} strokeWidth={1.75} fill="currentColor" /> : <Mic size={18} strokeWidth={1.75} />}
              </button>
            )}
          </div>
          {dictation.state === "listening" && <span className="text-[0.875rem] text-teal-strong">{dictation.transcript || "Listening…"}</span>}
          {dictation.error && <span className="text-[0.875rem] text-ink-3">{dictation.error}</span>}
        </label>

        <div className={styles.grid2}>
          <label className={field.field}>
            <span className={field.label}>Age</span>
            <input className={`${field.input} tnum`} type="number" inputMode="numeric" min={0} max={120} value={age} onChange={(e) => setAge(e.target.value)} placeholder="—" />
          </label>
          <div className={field.field}>
            <span className={field.label}>Sex</span>
            <Segmented
              label="Sex"
              value={sex}
              onChange={setSex}
              className="w-full"
              options={[
                { value: "F", label: "Female" },
                { value: "M", label: "Male" },
                { value: "X", label: "Other" },
              ]}
            />
          </div>
        </div>

        <div className={styles.route}>
          <label className={field.field}>
            <span className={field.label}>From</span>
            <select className={field.select} value={chosenOrigin} onChange={(e) => setOrigin(e.target.value)}>
              {origins.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.short_name}
                </option>
              ))}
            </select>
          </label>
          <ArrowRight size={18} strokeWidth={1.75} className={styles.routeArrow} aria-hidden />
          <label className={field.field}>
            <span className={field.label}>To</span>
            <select className={field.select} value={chosenDest} onChange={(e) => setDest(e.target.value)}>
              {hospitals.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.short_name}
                </option>
              ))}
            </select>
          </label>
        </div>

        <div className={field.field}>
          <span className={field.label}>Transport</span>
          <div className={styles.modes} role="radiogroup" aria-label="Transport">
            {(region?.modes ?? []).map((m) => (
              <button key={m} type="button" role="radio" aria-checked={chosenMode === m} className={styles.mode} onClick={() => setMode(m)}>
                <ModeIcon mode={m} size={22} />
                {MODE_LABEL[m]}
              </button>
            ))}
          </div>
        </div>

        <ButtonPrimary size="lg" className="w-full" disabled={!ready || busy} onClick={start}>
          {busy ? <Loader2 size={18} strokeWidth={1.75} className="animate-spin" /> : null}
          Begin assessment <ArrowRight size={18} strokeWidth={1.75} />
        </ButtonPrimary>
      </section>
    </div>
  );
}
