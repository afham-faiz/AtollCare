// F-M5.1 "Hold to speak": MediaRecorder (webm/opus) → /api/voice/transcribe (ElevenLabs Scribe, mock in demo).
"use client";

import { Loader2, Mic } from "lucide-react";
import { useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import { api } from "@/lib/api";
import { toast, toastError } from "@/lib/toast";

export default function ({
  caseId,
  language,
  onText,
  className,
}: {
  caseId?: string;
  language?: string;
  onText: (text: string) => void;
  className?: string;
}) {
  const [state, setState] = useState<"idle" | "recording" | "uploading">("idle");
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);

  const start = async () => {
    if (state !== "idle") return;
    if (!navigator.mediaDevices?.getUserMedia) {
      toast("Microphone not available in this browser — please type instead", "warn");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      const r = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunks.current = [];
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunks.current, { type: r.mimeType || "audio/webm" });
        if (blob.size < 500) {
          setState("idle");
          toast("Hold the button while you speak", "warn");
          return;
        }
        setState("uploading");
        const form = new FormData();
        form.append("audio", blob, "voice.webm");
        if (language) form.append("language", language);
        if (caseId) form.append("case_id", caseId);
        try {
          const res = await api<{ text: string; source: string }>("/voice/transcribe", { method: "POST", body: form });
          onText(res.text);
          if (res.source === "mock") toast("Mock transcription (ElevenLabs in mock mode)", "info", 3000);
        } catch (err) {
          toastError(err);
        } finally {
          setState("idle");
        }
      };
      rec.current = r;
      r.start();
      setState("recording");
    } catch {
      toast("Microphone permission denied — please type instead", "warn");
    }
  };

  const stop = () => {
    if (rec.current?.state === "recording") rec.current.stop();
  };

  return (
    <button
      type="button"
      onPointerDown={start}
      onPointerUp={stop}
      onPointerLeave={stop}
      onKeyDown={(e) => (e.key === " " || e.key === "Enter") && !e.repeat && start()}
      onKeyUp={(e) => (e.key === " " || e.key === "Enter") && stop()}
      disabled={state === "uploading"}
      className={twMerge(
        "inline-flex min-h-[3rem] select-none items-center justify-center gap-[.5rem] rounded-[.5rem] border-[1px] border-brand px-[1rem] font-medium text-brand touch-none",
        state === "recording" && "bg-alert border-alert text-white",
        className,
      )}
    >
      {state === "uploading" ? <Loader2 size={20} className="animate-spin" /> : <Mic size={20} />}
      {state === "recording" ? "Listening… release to send" : state === "uploading" ? "Transcribing…" : "Hold to speak"}
    </button>
  );
}
