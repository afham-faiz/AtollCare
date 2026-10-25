// What the camera can't measure: SpO₂, blood pressure, temperature, ACVPU, oxygen. Completes NEWS2. The oximeter's
// pulse, when given, is also checked against the camera's heart rate (and wins if they disagree).
// Said or typed: the microphone fills the fields (ElevenLabs writes it down, the engine reads the numbers), and nothing
// is recorded until Save.
"use client";

import { Loader2, Mic, Square } from "lucide-react";
import { useCallback, useState } from "react";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import Segmented from "@/app/components/(controls)/Segmented";
import ModalPrimary from "@/app/components/(modals)/ModalPrimary";
import { api, post, type HeardVitals, type VitalsRequest } from "@/lib/api";
import { useAudioLevels } from "@/lib/audio";
import { useDictation, type DictationResult } from "@/lib/dictation";
import { useMeta } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./VitalsSheet.module.scss";

type Acvpu = "A" | "C" | "V" | "P" | "U";
type Key = "spo2" | "pulse" | "sbp" | "temp" | "oxygen" | "acvpu";

export default function ({ transferId, open, onClose, onSaved }: { transferId: string; open: boolean; onClose: () => void; onSaved: () => void }) {
  const { data: meta } = useMeta();
  const [spo2, setSpo2] = useState("");
  const [pulse, setPulse] = useState("");
  const [sbp, setSbp] = useState("");
  const [temp, setTemp] = useState("");
  const [acvpu, setAcvpu] = useState<Acvpu | null>(null);
  const [oxygen, setOxygen] = useState<"air" | "oxygen">("air");
  const [busy, setBusy] = useState(false);
  // what the microphone heard, and which fields it filled (they glow until edited)
  const [reading, setReading] = useState(false);
  const [heard, setHeard] = useState<{ transcript: string; filled: number } | null>(null);
  const [filled, setFilled] = useState<Set<Key>>(new Set());

  const apply = (h: HeardVitals) => {
    const got = new Set<Key>();
    const num = (v: number | null | undefined, set: (s: string) => void, key: Key) => {
      if (v == null) return;
      set(String(v));
      got.add(key);
    };
    num(h.spo2, setSpo2, "spo2");
    num(h.heart_rate, setPulse, "pulse");
    num(h.systolic_bp, setSbp, "sbp");
    num(h.temperature_c, setTemp, "temp");
    if (h.on_oxygen != null) {
      setOxygen(h.on_oxygen ? "oxygen" : "air");
      got.add("oxygen");
    }
    if (h.consciousness) {
      setAcvpu(h.consciousness);
      got.add("acvpu");
    }
    setFilled(got);
    setHeard({ transcript: h.transcript, filled: got.size });
  };

  const listen = useCallback(async (r: DictationResult) => {
    setReading(true);
    try {
      let h: HeardVitals;
      if (r.kind === "audio") {
        const form = new FormData();
        form.append("audio", r.blob, "vitals.webm");
        h = await api<HeardVitals>("/transfers/vitals/heard/voice", { method: "POST", body: form });
      } else {
        h = await post<HeardVitals>("/transfers/vitals/heard", { text: r.text });
      }
      apply(h);
    } catch (err) {
      toastError(err);
    } finally {
      setReading(false);
    }
  }, []);

  const dictation = useDictation(meta?.adapters.elevenlabs === "real", listen);
  const listening = dictation.state === "listening";
  const levels = useAudioLevels(listening);

  const edited = (key: Key) =>
    setFilled((s) => {
      if (!s.has(key)) return s;
      const next = new Set(s);
      next.delete(key);
      return next;
    });

  const reset = () => {
    setSpo2("");
    setPulse("");
    setSbp("");
    setTemp("");
    setAcvpu(null);
    setHeard(null);
    setFilled(new Set());
  };

  const save = async () => {
    const body: VitalsRequest = { source: "manual", on_oxygen: oxygen === "oxygen" };
    if (spo2) body.spo2 = Number(spo2);
    if (pulse) body.heart_rate = Number(pulse);
    if (sbp) body.systolic_bp = Number(sbp);
    if (temp) body.temperature_c = Number(temp);
    if (acvpu) body.consciousness = acvpu;
    setBusy(true);
    try {
      await post(`/transfers/${transferId}/vitals`, body);
      onSaved();
      onClose();
      reset();
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
    }
  };

  const numberField = (key: Key, label: string, value: string, set: (v: string) => void, props: React.JSX.IntrinsicElements["input"]) => (
    <label className={field.field}>
      <span className={field.label}>{label}</span>
      <input
        className={twMerge(field.input, "tnum", filled.has(key) && styles.filled)}
        type="number"
        value={value}
        onChange={(e) => {
          set(e.target.value);
          edited(key);
        }}
        {...props}
      />
    </label>
  );

  return (
    <ModalPrimary
      open={open}
      onClose={() => {
        dictation.stop();
        onClose();
      }}
      title="Crew vitals"
      subtitle="Values the camera can't measure"
      footer={
        <>
          <ButtonBase onClick={onClose}>Cancel</ButtonBase>
          <ButtonPrimary onClick={save} disabled={busy || listening || reading || (!spo2 && !pulse && !sbp && !temp && !acvpu)}>
            Save
          </ButtonPrimary>
        </>
      }
    >
      {dictation.supported && (
        <div className={twMerge(styles.say, listening && styles.sayLive)}>
          <button
            type="button"
            className={twMerge(styles.mic, listening && styles.micLive)}
            onClick={dictation.toggle}
            disabled={reading}
            aria-pressed={listening}
            aria-label={listening ? "Stop and fill in" : "Say the vitals"}
          >
            {reading ? <Loader2 size={20} strokeWidth={1.75} className="animate-spin" /> : listening ? <Square size={16} strokeWidth={1.75} fill="currentColor" /> : <Mic size={20} strokeWidth={1.75} />}
          </button>
          <div className={styles.sayBody} aria-live="polite">
            {listening ? (
              <>
                <div className={styles.meter} aria-hidden>
                  {levels.map((l, i) => (
                    <span key={i} style={{ transform: `scaleY(${0.12 + l * 0.88})` }} />
                  ))}
                </div>
                <p className={styles.sayHint}>{dictation.transcript || "Listening. Tap to fill in"}</p>
              </>
            ) : reading ? (
              <p className={styles.sayTitle}>Reading the numbers…</p>
            ) : heard ? (
              <>
                <p className={styles.sayTitle}>{heard.filled ? `Filled ${heard.filled} from what you said. Check, then save` : "No vitals heard in that"}</p>
                <p className={styles.sayHint}>“{heard.transcript}”</p>
              </>
            ) : (
              <>
                <p className={styles.sayTitle}>Say them</p>
                <p className={styles.sayHint}>“Sats 94 on air, BP 120 over 80, temp 37.2, alert”</p>
              </>
            )}
            {dictation.error && <p className={styles.sayHint}>{dictation.error}</p>}
          </div>
        </div>
      )}
      <div className="grid grid-cols-2 gap-[.75rem] sm:grid-cols-4">
        {numberField("spo2", "SpO₂ %", spo2, setSpo2, { inputMode: "numeric", min: 50, max: 100 })}
        {numberField("pulse", "Pulse (oximeter)", pulse, setPulse, { inputMode: "numeric", min: 20, max: 250 })}
        {numberField("sbp", "Systolic BP", sbp, setSbp, { inputMode: "numeric", min: 40, max: 280 })}
        {numberField("temp", "Temp °C", temp, setTemp, { inputMode: "decimal", step: "0.1", min: 30, max: 44 })}
      </div>
      <div className={field.field}>
        <span className={field.label}>Breathing</span>
        <Segmented
          label="Air or oxygen"
          value={oxygen}
          onChange={(v) => {
            setOxygen(v);
            edited("oxygen");
          }}
          className={twMerge(filled.has("oxygen") && styles.filledTrack)}
          options={[
            { value: "air", label: "Room air" },
            { value: "oxygen", label: "On oxygen" },
          ]}
        />
      </div>
      <div className={field.field}>
        <span className={field.label}>Consciousness (ACVPU)</span>
        <Segmented
          label="ACVPU"
          value={acvpu}
          onChange={(v) => {
            setAcvpu(v);
            edited("acvpu");
          }}
          className={twMerge("w-full", filled.has("acvpu") && styles.filledTrack)}
          options={[
            { value: "A", label: "Alert" },
            { value: "C", label: "Confused" },
            { value: "V", label: "Voice" },
            { value: "P", label: "Pain" },
            { value: "U", label: "None" },
          ]}
        />
      </div>
    </ModalPrimary>
  );
}
