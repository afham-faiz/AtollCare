// F-M1.8 Live status for family: stepper, ETA countdown, spoken update (ElevenLabs), shareable link + QR.
"use client";

import { Share2 } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { useEffect, useState } from "react";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import Card from "@/app/components/Card";
import { api, type Case } from "@/lib/api";
import { fmtMin, fmtTime } from "@/lib/format";
import { playUrlOrSpeak } from "@/lib/speech";
import { toast, toastError } from "@/lib/toast";

import StatusStepper from "./StatusStepper";

export default function ({ c, now, showShare = true }: { c: Case; now?: string; showShare?: boolean }) {
  const [origin, setOrigin] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setOrigin(window.location.origin), []);
  const link = `${origin}/case/${c.id}`;
  const eta = c.transport.eta;
  const remaining = eta && now ? (new Date(eta).getTime() - new Date(now).getTime()) / 60000 : null;

  const speakUpdate = async () => {
    setBusy(true);
    try {
      const res = await api<{ text: string; audio_url: string | null }>(`/cases/${c.id}/status-sentence?speak=true`);
      await playUrlOrSpeak(res.audio_url, res.text);
    } catch (err) {
      toastError(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Live status">
      <StatusStepper status={c.status} />
      {eta && c.transport.status !== "arrived" && (
        <p className="mt-[1rem] text-[1.25rem] font-semibold tabular-nums">
          ETA {fmtTime(eta)}
          {remaining !== null && remaining > 0 && <span className="text-muted"> · in {fmtMin(remaining)}</span>}
        </p>
      )}
      <div className="mt-[1rem] flex flex-wrap gap-[.5rem]">
        <ButtonBase onClick={speakUpdate} disabled={busy}>
          {busy ? "Speaking…" : "Speak update"}
        </ButtonBase>
        {showShare && (
          <ButtonBase
            onClick={async () => {
              try {
                if (navigator.share) await navigator.share({ title: `Case ${c.short_code}`, url: link });
                else {
                  await navigator.clipboard.writeText(link);
                  toast("Family link copied");
                }
              } catch {
                // share cancelled
              }
            }}
          >
            <Share2 size={20} /> Share family link
          </ButtonBase>
        )}
      </div>
      {showShare && origin && (
        <div className="mt-[1rem] flex items-center gap-[1rem]">
          <div className="rounded-[.5rem] bg-white p-[.5rem]">
            <QRCodeSVG value={link} size={112} />
          </div>
          <p className="text-[0.875rem] text-muted">Read-only status page for family. No personal data in the link.</p>
        </div>
      )}
    </Card>
  );
}
