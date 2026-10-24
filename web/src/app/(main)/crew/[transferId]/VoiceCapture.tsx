// One control: tap, speak, tap. Real microphone level, live transcript, then the note returns structured.
"use client";

import { Check, HelpCircle, Keyboard, Loader2, Mic, Send, Square } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";

import { api, post, type Note, type Transfer } from "@/lib/api";
import { useAudioLevels } from "@/lib/audio";
import { useDictation, type DictationResult } from "@/lib/dictation";
import { toastError } from "@/lib/toast";

import styles from "./VoiceCapture.module.scss";

export default function ({
  transferId,
  serverStt,
  question,
  askedBy,
  onSaved,
  disabled,
}: {
  transferId: string;
  serverStt: boolean;
  question: Note | null;
  askedBy: string;
  onSaved: (t: Transfer) => void;
  disabled?: boolean;
}) {
  const [saving, setSaving] = useState(false);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [result, setResult] = useState<Note | null>(null);
  const [seconds, setSeconds] = useState(0);

  // typed notes are stored as "text" and dictated ones as "voice", so the record shows how each note was captured
  const send = useCallback(
    async (r: DictationResult, typed = false) => {
      setSaving(true);
      try {
        let t: Transfer;
        if (r.kind === "audio") {
          const form = new FormData();
          form.append("audio", r.blob, "note.webm");
          if (question) form.append("reply_to", question.id);
          t = await api<Transfer>(`/transfers/${transferId}/notes/voice`, { method: "POST", body: form });
        } else {
          t = await post<Transfer>(`/transfers/${transferId}/notes`, { text: r.text, kind: typed ? "text" : "voice", reply_to: question?.id ?? null });
        }
        const mine = [...t.notes].reverse().find((n) => n.author === "crew" && n.kind !== "event");
        setResult(mine ?? null);
        onSaved(t);
      } catch (err) {
        toastError(err);
      } finally {
        setSaving(false);
      }
    },
    [transferId, question, onSaved],
  );

  const dictation = useDictation(serverStt, send);
  const listening = dictation.state === "listening";
  const levels = useAudioLevels(listening);

  useEffect(() => {
    if (!listening) return;
    const started = Date.now();
    const t = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 250);
    return () => {
      window.clearInterval(t);
      setSeconds(0);
    };
  }, [listening]);

  useEffect(() => {
    if (!result) return;
    const t = window.setTimeout(() => setResult(null), 9000);
    return () => window.clearTimeout(t);
  }, [result]);

  const chips = useMemo(() => [...(result?.extraction?.interventions ?? []), ...(result?.extraction?.observations ?? [])], [result]);
  const replying = !!question;
  const canVoice = dictation.supported && !typing;

  const submitTyped = async () => {
    if (!text.trim()) return;
    await send({ kind: "text", text: text.trim() }, true);
    setText("");
    setTyping(false);
  };

  return (
    <div className={styles.capture}>
      {canVoice ? (
        <button
          type="button"
          onClick={dictation.toggle}
          disabled={saving || disabled}
          aria-pressed={listening}
          aria-label={listening ? "Stop recording" : replying ? `Answer ${askedBy}` : "Record a note"}
          className={twMerge(styles.record, listening && styles.recording, replying && !listening && styles.reply)}
        >
          {saving ? <Loader2 size={22} className="animate-spin" /> : listening ? <Square size={18} fill="currentColor" /> : <Mic size={22} />}
        </button>
      ) : (
        <span className={twMerge(styles.record, styles.typeIcon)} aria-hidden>
          <Keyboard size={20} />
        </span>
      )}

      <div className={styles.body}>
        {typing || !dictation.supported ? (
          <form
            className={styles.typed}
            onSubmit={(e) => {
              e.preventDefault();
              submitTyped();
            }}
          >
            <input
              autoFocus
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={replying ? `Answer ${askedBy}…` : "e.g. Gave aspirin 300 mg, pain 8 out of 10"}
              aria-label="Note"
            />
            <button type="submit" disabled={saving || !text.trim()} aria-label="Add note" className={styles.sendTyped}>
              {saving ? <Loader2 size={18} className="animate-spin" /> : <Send size={18} />}
            </button>
          </form>
        ) : listening ? (
          <div className={styles.live}>
            <div className={styles.meter} aria-hidden>
              {levels.map((l, i) => (
                <span key={i} style={{ transform: `scaleY(${0.12 + l * 0.88})` }} />
              ))}
            </div>
            <span className={twMerge("tnum", styles.timer)}>
              {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
            </span>
            <p className={styles.transcript}>{dictation.transcript || (serverStt ? "Recording — tap to finish" : "Listening…")}</p>
          </div>
        ) : saving ? (
          <p className={styles.primaryLine}>Structuring note…</p>
        ) : result ? (
          <div className={styles.result} key={result.id}>
            <p className={styles.primaryLine}>
              <Check size={16} strokeWidth={2.6} className="text-teal" /> {result.kind === "answer" ? "Answer sent" : "Added to handoff"}
            </p>
            {chips.length > 0 ? (
              <div className={styles.chips}>
                {chips.slice(0, 5).map((c, i) => (
                  <span key={c} className={styles.chip} style={{ animationDelay: `${i * 60}ms` }}>
                    {c}
                  </span>
                ))}
              </div>
            ) : (
              <p className={styles.secondaryLine}>“{result.text}”</p>
            )}
          </div>
        ) : replying ? (
          <div className={styles.ask} key={question.id} role="status">
            <p className={styles.askFrom}>
              <HelpCircle size={14} strokeWidth={2.4} className="shrink-0" />
              <span className="truncate">
                {askedBy} asks<span className="max-lg:hidden"> · tap to answer</span>
              </span>
            </p>
            <p className={styles.askText}>{question.text.split(": ").slice(1).join(": ") || question.text}</p>
            {dictation.error && <p className={styles.secondaryLine}>{dictation.error}</p>}
          </div>
        ) : (
          <>
            <p className={styles.primaryLine}>Speak a note</p>
            <p className={styles.secondaryLine}>{dictation.error ?? "Drugs given and findings are added to the handoff."}</p>
          </>
        )}
      </div>

      {dictation.supported && !listening && (
        <button type="button" className={styles.toggle} onClick={() => setTyping((v) => !v)} aria-label={typing ? "Use voice" : "Type instead"} title={typing ? "Use voice" : "Type instead"}>
          {typing ? <Mic size={18} /> : <Keyboard size={18} />}
        </button>
      )}
    </div>
  );
}
