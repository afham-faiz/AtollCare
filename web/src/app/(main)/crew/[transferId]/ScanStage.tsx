// Contactless vitals by scan: a 60 s clip from a propped-up phone, analysed on the server (Presage heart and breathing
// rate, Gemini's check for visible signs). The phone-first alternative to the live camera; the readings land on the
// transfer timed when the clip was recorded, and only a good signal is scored.
"use client";

import { ChevronDown, Loader2, RotateCcw } from "lucide-react";
import { useState } from "react";

import ScanRecorder from "@/app/components/(scan)/ScanRecorder";
import ScanResult from "@/app/components/(scan)/ScanResult";
import { api, type Transfer } from "@/lib/api";
import { toastError } from "@/lib/toast";

import styles from "./ScanStage.module.scss";

export default function ({ t, tz, onSaved }: { t: Transfer; tz?: string; onSaved: (next: Transfer) => void }) {
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  const latest = t.scans.at(-1);
  const earlier = t.scans.slice(0, -1).reverse();
  const finished = t.status === "arrived" || t.status === "closed";

  const upload = async (clip: Blob, filename: string) => {
    setUploading(true);
    const form = new FormData();
    form.append("video", clip, filename);
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
          <h2 className={styles.title}>{latest ? "Measure again" : "Measure with a 60-second scan"}</h2>
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
        <button type="button" className={styles.again} onClick={() => setRecording(true)} disabled={latest?.status === "processing"}>
          <RotateCcw size={16} /> Measure again
        </button>
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
