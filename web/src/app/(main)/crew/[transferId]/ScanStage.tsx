// Contactless vitals by scan: a 60 s clip from a propped-up phone, analysed on the server (Presage heart and breathing
// rate, Gemini's check for visible signs). The phone-first alternative to the live camera; the readings land on the
// transfer timed when the clip was recorded, and only a good signal is scored.
"use client";

import { ChevronDown, Loader2, RotateCcw } from "lucide-react";
import { useState } from "react";

import ScanRecorder from "@/app/components/(scan)/ScanRecorder";
import ScanResult from "@/app/components/(scan)/ScanResult";
import { api, type Transfer } from "@/lib/api";
import type { PresageSummary } from "@/lib/presage";
import { toastError } from "@/lib/toast";

import styles from "./ScanStage.module.scss";

// how often to re-scan: every 30 min when NEWS2 is low, 15 when medium, 5 when high or the camera trend is worrying
function scanEveryMin(t: Transfer): number {
  if (t.alerts.some((a) => a.code === "presage_trend")) return 5;
  const total = t.news2?.total ?? 0;
  return total >= 7 ? 5 : total >= 5 ? 15 : 30;
}

export default function ({ t, tz, now, onSaved }: { t: Transfer; tz?: string; now?: string; onSaved: (next: Transfer) => void }) {
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const latest = t.scans.at(-1);
  const earlier = t.scans.slice(0, -1).reverse();
  const finished = t.status === "arrived" || t.status === "closed";
  const every = scanEveryMin(t);
  const dueIn = latest && now ? Math.round((new Date(latest.at).getTime() + every * 60000 - new Date(now).getTime()) / 60000) : null;

  const upload = async (clip: Blob, filename: string, presage: PresageSummary | null) => {
    setUploading(true);
    const form = new FormData();
    form.append("video", clip, filename);
    if (presage) form.append("presage", JSON.stringify(presage)); // measured live while recording
    try {
      onSaved(await api<Transfer>(`/transfers/${t.id}/scans`, { method: "POST", body: form }));
      setRecording(false);
    } catch (err) {
      toastError(err);
    } finally {
      setUploading(false);
    }
  };

  if ((!latest || recording) && !finished) {
    return (
      <section className={styles.stage} aria-label="Scan">
        <header className={styles.head}>
          <h2 className={styles.title}>{latest ? "Measure again" : "Measure with the phone camera"}</h2>
          {latest && (
            <button type="button" className={styles.link} onClick={() => setRecording(false)} disabled={uploading}>
              Cancel
            </button>
          )}
        </header>
        <ScanRecorder onClip={upload} disabled={uploading} />
        {uploading && (
          <p className={styles.uploading}>
            <Loader2 size={16} className="animate-spin" /> Sending the video…
          </p>
        )}
      </section>
    );
  }

  return (
    <section className={styles.stage} aria-label="Scans">
      {latest ? (
        <ScanResult scan={latest} tz={tz} title={t.scans.length > 1 ? `Scan ${t.scans.length}` : "Scan"} coach />
      ) : (
        <p className={styles.empty}>No scans were taken on this transfer.</p>
      )}
      {!finished && (
        <div className={styles.againRow}>
          <button type="button" className={styles.again} onClick={() => setRecording(true)} disabled={latest?.status === "processing"}>
            <RotateCcw size={16} /> Measure again
          </button>
          {dueIn !== null && (
            <span className={dueIn <= 0 ? styles.due : styles.dueLater}>
              {dueIn <= 0 ? "Next scan due now" : `Next scan in ${dueIn} min`} · every {every} min at this acuity
            </span>
          )}
        </div>
      )}
      {earlier.length > 0 && (
        <details className={styles.earlier}>
          <summary>
            Earlier scans ({earlier.length}) <ChevronDown size={14} />
          </summary>
          <div className={styles.earlierList}>
            {earlier.map((s, i) => (
              <ScanResult key={s.id} scan={s} tz={tz} title={`Scan ${earlier.length - i}`} />
            ))}
          </div>
        </details>
      )}
    </section>
  );
}
