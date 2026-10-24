// F-M5.2 Speak text: ElevenLabs audio from the engine, or window.speechSynthesis when the engine returns null.
"use client";

import { post } from "@/lib/api";

let current: HTMLAudioElement | null = null;

export function stopSpeaking() {
  current?.pause();
  current = null;
  if (typeof window !== "undefined") window.speechSynthesis?.cancel();
}

function browserSpeak(text: string, lang?: string): Promise<void> {
  return new Promise((resolve) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return resolve();
    const u = new SpeechSynthesisUtterance(text);
    if (lang) u.lang = lang;
    u.rate = 0.95;
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

export async function speak(
  text: string,
  voice: "guide" | "status" = "guide",
  language?: string,
): Promise<"elevenlabs" | "browser"> {
  stopSpeaking();
  let url: string | null = null;
  try {
    const res = await post<{ audio_url: string | null }>("/voice/speak", { text, voice, language });
    url = res.audio_url;
  } catch {
    url = null;
  }
  if (!url) {
    await browserSpeak(text, language);
    return "browser";
  }
  await new Promise<void>((resolve) => {
    const audio = new Audio(url!);
    current = audio;
    audio.onended = () => resolve();
    audio.onerror = () => browserSpeak(text, language).then(resolve);
    audio.play().catch(() => browserSpeak(text, language).then(resolve));
  });
  return "elevenlabs";
}

export async function playUrlOrSpeak(url: string | null | undefined, text: string) {
  stopSpeaking();
  if (!url) return browserSpeak(text);
  const audio = new Audio(url);
  current = audio;
  await audio.play().catch(() => browserSpeak(text));
}
