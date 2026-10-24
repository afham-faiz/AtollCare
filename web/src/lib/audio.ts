// Real microphone level while recording (Web Audio analyser) — drives the voice meter. No fake waveform.
"use client";

import { useEffect, useRef, useState } from "react";

const BARS = 28;

export function useAudioLevels(active: boolean): number[] {
  const [levels, setLevels] = useState<number[]>(() => Array(BARS).fill(0));
  const history = useRef<number[]>(Array(BARS).fill(0));

  useEffect(() => {
    if (!active || !navigator.mediaDevices?.getUserMedia) return;
    let stream: MediaStream | null = null;
    let ctx: AudioContext | null = null;
    let frame = 0;
    let cancelled = false;
    (async () => {
      try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        if (cancelled) return;
        ctx = new AudioContext();
        const analyser = ctx.createAnalyser();
        analyser.fftSize = 512;
        ctx.createMediaStreamSource(stream).connect(analyser);
        const data = new Uint8Array(analyser.fftSize);
        let last = 0;
        const loop = (now: number) => {
          frame = requestAnimationFrame(loop);
          if (now - last < 60) return; // ~16 updates/s is plenty and cheap
          last = now;
          analyser.getByteTimeDomainData(data);
          let sum = 0;
          for (const v of data) sum += ((v - 128) / 128) ** 2;
          const rms = Math.min(1, Math.sqrt(sum / data.length) * 4.5);
          history.current = [...history.current.slice(1), rms];
          setLevels(history.current);
        };
        frame = requestAnimationFrame(loop);
      } catch {
        // permission denied / no device: the meter stays flat (the dictation hook reports the error)
      }
    })();
    return () => {
      cancelled = true;
      cancelAnimationFrame(frame);
      stream?.getTracks().forEach((t) => t.stop());
      ctx?.close().catch(() => undefined);
      history.current = Array(BARS).fill(0);
      setLevels(history.current);
    };
  }, [active]);

  return levels;
}
