// One big button: tap, speak, tap again. Notes go to the hospital; answers attach to the open question.
"use client";

import { Keyboard, Loader2, Mic, Send, Square } from "lucide-react";
import { useCallback, useState } from "react";
import { twMerge } from "tailwind-merge";

import { api, post, type Note, type Transfer } from "@/lib/api";
import { useDictation, type DictationResult } from "@/lib/dictation";
import { toastError } from "@/lib/toast";

import styles from "./VoiceBar.module.scss";

export default function ({
  transferId,
  serverStt,
  question,
  onSaved,
}: {
  transferId: string;
  serverStt: boolean;
  question: Note | null;
  onSaved: (t: Transfer) => void;
}) {
  const [saving, setSaving] = useState(false);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");

  const send = useCallback(
    async (r: DictationResult) => {
      setSaving(true);
      try {
        let t: Transfer;
        if (r.kind === "audio") {
          const form = new FormData();
          form.append("audio", r.blob, "note.webm");
          if (question) form.append("reply_to", question.id);
          t = await api<Transfer>(`/transfers/${transferId}/notes/voice`, { method: "POST", body: form });
        } else {
          t = await post<Transfer>(`/transfers/${transferId}/notes`, {
            text: r.text,
            kind: "voice",
            reply_to: question?.id ?? null,
          });
        }
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

  const submitTyped = async () => {
    if (!text.trim()) return;
    await send({ kind: "text", text: text.trim() });
    setText("");
    setTyping(false);
  };

  const label = question ? "Answer the hospital" : "Speak a note";

  return (
    <div className={styles.bar}>
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
            placeholder={question ? "Type your answer…" : "Type a note, e.g. Gave aspirin 300 mg"}
          />
          <button type="submit" className={styles.send} disabled={saving || !text.trim()} aria-label="Send note">
            {saving ? <Loader2 size={20} className="animate-spin" /> : <Send size={20} />}
          </button>
        </form>
      ) : (
        <button
          type="button"
          onClick={dictation.toggle}
          disabled={saving}
          className={twMerge(styles.mic, listening && styles.listening, question && styles.answer)}
          aria-pressed={listening}
        >
          {saving ? <Loader2 size={28} className="animate-spin" /> : listening ? <Square size={26} /> : <Mic size={28} />}
          <span>{saving ? "Saving…" : listening ? "Tap to finish" : label}</span>
        </button>
      )}
      <div className={styles.side}>
        <p className={styles.transcript}>
          {listening
            ? dictation.transcript || (serverStt ? "Recording… speak clearly, tap again to send." : "Listening…")
            : dictation.error ?? (question ? `Answering: “${question.text.split(": ").slice(1).join(": ") || question.text}”` : "Interventions and observations are picked out automatically.")}
        </p>
        {dictation.supported && (
          <button type="button" className={styles.toggle} onClick={() => setTyping((v) => !v)}>
            <Keyboard size={16} /> {typing ? "Use voice" : "Type instead"}
          </button>
        )}
      </div>
    </div>
  );
}
