// Crew voice notes. Tap to start, tap to stop.
//   ElevenLabs configured → record (MediaRecorder) and upload; the engine transcribes with Scribe.
//   Otherwise           → the browser's own speech recognition, with a live transcript.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Recognition = {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((e: { resultIndex: number; results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
};

function recognitionCtor(): (new () => Recognition) | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: new () => Recognition; webkitSpeechRecognition?: new () => Recognition };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

export type DictationResult = { kind: "text"; text: string } | { kind: "audio"; blob: Blob };

export function useDictation(serverStt: boolean, onResult: (r: DictationResult) => void) {
  const [state, setState] = useState<"idle" | "listening" | "error">("idle");
  const [transcript, setTranscript] = useState("");
  const [error, setError] = useState<string | null>(null);
  const recRef = useRef<Recognition | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const finalRef = useRef("");
  const resultRef = useRef(onResult);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    resultRef.current = onResult;
  }, [onResult]);

  useEffect(() => {
    const ok = serverStt ? typeof MediaRecorder !== "undefined" : recognitionCtor() !== null;
    // feature detection must run on the client after hydration
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSupported(ok);
  }, [serverStt]);

  const start = useCallback(async () => {
    setError(null);
    setTranscript("");
    finalRef.current = "";
    if (serverStt) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
        const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
        const chunks: Blob[] = [];
        rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
        rec.onstop = () => {
          stream.getTracks().forEach((t) => t.stop());
          setState("idle");
          const blob = new Blob(chunks, { type: rec.mimeType || "audio/webm" });
          if (blob.size > 1000) resultRef.current({ kind: "audio", blob });
        };
        mediaRef.current = rec;
        rec.start();
        setState("listening");
      } catch {
        setError("Microphone blocked — allow it in the browser, or type the note");
        setState("error");
      }
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor) {
      setError("Voice notes need Chrome or Edge here — type the note instead");
      setState("error");
      return;
    }
    const rec = new Ctor();
    rec.continuous = true;
    rec.interimResults = true;
    rec.lang = "en-GB";
    rec.onresult = (e) => {
      let interim = "";
      for (let i = e.resultIndex; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalRef.current += r[0].transcript;
        else interim += r[0].transcript;
      }
      setTranscript((finalRef.current + interim).trim());
    };
    rec.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return;
      setError(e.error === "not-allowed" ? "Microphone blocked — allow it in the browser" : `Voice error: ${e.error}`);
    };
    rec.onend = () => {
      setState("idle");
      const text = finalRef.current.trim();
      if (text) resultRef.current({ kind: "text", text });
    };
    recRef.current = rec;
    rec.start();
    setState("listening");
  }, [serverStt]);

  const stop = useCallback(() => {
    if (mediaRef.current?.state === "recording") mediaRef.current.stop();
    recRef.current?.stop();
  }, []);

  const toggle = useCallback(() => (state === "listening" ? stop() : start()), [state, start, stop]);

  return { state, transcript, error, supported, toggle, stop };
}
