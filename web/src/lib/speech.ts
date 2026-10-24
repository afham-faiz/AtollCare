// Spoken output in the vehicle: ElevenLabs audio from the engine, or the browser's speechSynthesis when the engine
// has no ElevenLabs key. Utterances are queued so a question and an alert never talk over each other.
"use client";

import { post } from "@/lib/api";

let chain: Promise<void> = Promise.resolve();
let current: HTMLAudioElement | null = null;

function browserSpeak(text: string): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = "en-GB";
    u.rate = 1;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

async function speakNow(text: string, voice: "crew" | "hospital"): Promise<void> {
  let url: string | null = null;
  try {
    url = (await post<{ audio_url: string | null }>("/voice/speak", { text, voice })).audio_url;
  } catch {
    url = null;
  }
  if (!url) return browserSpeak(text);
  await new Promise<void>((resolve) => {
    const audio = new Audio(url!);
    current = audio;
    audio.onended = () => resolve();
    audio.onerror = () => browserSpeak(text).then(resolve);
    audio.play().catch(() => browserSpeak(text).then(resolve));
  });
}

export function speak(text: string, voice: "crew" | "hospital" = "hospital"): Promise<void> {
  chain = chain.then(() => speakNow(text, voice));
  return chain;
}

export function stopSpeaking() {
  current?.pause();
  current = null;
  if (typeof window !== "undefined") window.speechSynthesis?.cancel();
  chain = Promise.resolve();
}
