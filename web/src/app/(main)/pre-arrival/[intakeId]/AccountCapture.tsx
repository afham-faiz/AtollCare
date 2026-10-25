// Step 2: what happened, in the companion's own words. Tap, speak, tap — transcribed on the server (Scribe, or
// Gemini as a fallback). Typing always works. The words are kept as said; a one-line summary is made from them.
"use client";

import { Keyboard, Loader2, Mic, Square } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import field from "@/app/components/(controls)/Field.module.scss";
import { api, ApiError, patch, type Intake } from "@/lib/api";
import { useAudioLevels } from "@/lib/audio";
import { toast, toastError } from "@/lib/toast";

import styles from "../PreArrival.module.scss";

const AUDIO_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];

export default function ({ intake, onSaved }: { intake: Intake; onSaved: (i: Intake) => void }) {
  const [mode, setMode] = useState<"idle" | "recording" | "sending" | "typing">("idle");
  const [text, setText] = useState(intake.account ?? "");
  const [seconds, setSeconds] = useState(0);
  const recorder = useRef<MediaRecorder | null>(null);
  const levels = useAudioLevels(mode === "recording");

  useEffect(() => {
    if (mode !== "recording") return;
    const started = Date.now();
    const t = window.setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 250);
    return () => {
      window.clearInterval(t);
      setSeconds(0);
    };
  }, [mode]);

  const record = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const type = AUDIO_TYPES.find((t) => typeof MediaRecorder !== "undefined" && MediaRecorder.isTypeSupported(t)) ?? "";
      const r = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      const chunks: Blob[] = [];
      r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setMode("sending");
        const blob = new Blob(chunks, { type: r.mimeType || "audio/webm" });
        const form = new FormData();
        form.append("audio", blob, blob.type.includes("mp4") ? "account.m4a" : "account.webm");
        try {
          const next = await api<Intake>(`/intakes/${intake.id}/account/voice`, { method: "POST", body: form });
          setText(next.account ?? "");
          onSaved(next);
          setMode("idle");
        } catch (err) {
          if (err instanceof ApiError && (err.status === 501 || err.status === 422)) {
            toast(err.status === 501 ? "Voice isn't available here — please type it" : "Didn't catch that — try again or type it");
            setMode("typing");
          } else {
            toastError(err);
            setMode("idle");
          }
        }
      };
      recorder.current = r;
      r.start();
      setMode("recording");
    } catch {
      toast("Microphone isn't available — please type it");
      setMode("typing");
    }
  };

  const saveTyped = async () => {
    setMode("sending");
    try {
      onSaved(await patch<Intake>(`/intakes/${intake.id}`, { account: text.trim() }));
      setMode("idle");
    } catch (err) {
      toastError(err);
      setMode("typing");
    }
  };

  if (mode === "typing") {
    return (
      <div className={styles.stack}>
        <textarea
          className={field.textarea}
          autoFocus
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="e.g. He grabbed his chest about 40 minutes ago, he's sweating and says the pain goes to his left arm."
          aria-label="What happened"
        />
        <div className="flex gap-[.5rem]">
          <ButtonBase onClick={saveTyped} disabled={!text.trim()}>
            Save
          </ButtonBase>
          <ButtonBase onClick={() => setMode("idle")}>Cancel</ButtonBase>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.stack}>
      {intake.account && mode === "idle" && (
        <blockquote className={styles.account}>
          “{intake.account}”
          <span className={styles.accountMeta}>{intake.account_source === "voice" ? "Transcribed from your voice" : "Typed"}</span>
        </blockquote>
      )}
      <div className={styles.voice}>
        <button
          type="button"
          className={twMerge(styles.mic, intake.account && mode === "idle" && styles.micQuiet, mode === "recording" && styles.micLive)}
          onClick={mode === "recording" ? () => recorder.current?.stop() : record}
          disabled={mode === "sending"}
          aria-label={mode === "recording" ? "Stop recording" : "Record what happened"}
          // the halo follows the voice while recording
          style={mode === "recording" ? ({ "--level": Math.max(...levels, 0) } as React.CSSProperties) : undefined}
        >
          {mode === "sending" ? <Loader2 size={28} strokeWidth={1.75} className="animate-spin" /> : mode === "recording" ? <Square size={24} strokeWidth={1.75} fill="currentColor" /> : <Mic size={32} strokeWidth={1.75} />}
        </button>
        <p className={styles.voiceLabel}>
          {mode === "sending" ? (
            "Writing it down"
          ) : mode === "recording" ? (
            <>
              Listening · <span className="tnum">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}</span> · tap to finish
            </>
          ) : intake.account ? (
            "Tap to say it again"
          ) : (
            "Tap and speak"
          )}
        </p>
        {mode === "idle" && (
          <button type="button" className={styles.typeLink} onClick={() => setMode("typing")}>
            <Keyboard size={16} strokeWidth={1.75} /> {intake.account ? "Edit" : "or type it"}
          </button>
        )}
      </div>
    </div>
  );
}
