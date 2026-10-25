// Pre-arrival, first screen (the companion's phone): where are you taking them? Then the three steps.
"use client";

import { ArrowRight, Loader2, Phone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import { post, type Intake } from "@/lib/api";
import { useMeta } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./PreArrival.module.scss";

export default function ({ centre: fromLink }: { centre?: string }) {
  const router = useRouter();
  const { data: meta } = useMeta();
  const [picked, setPicked] = useState("");
  const [changing, setChanging] = useState(false);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const emergency = meta?.region.emergency_number;
  const linked = meta?.region.facilities.find((f) => f.id === fromLink);
  const centre = picked || linked?.id || "";
  // health centres first: that's where a companion usually heads; hospitals after
  const places = useMemo(
    () => [...(meta?.region.facilities ?? [])].sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === "clinic" ? -1 : 1)),
    [meta],
  );

  const start = async () => {
    setBusy(true);
    try {
      const i = await post<Intake>("/intakes", { health_centre_id: centre || null });
      router.push(`/pre-arrival/${i.id}`);
    } catch (err) {
      toastError(err);
      setBusy(false);
    }
  };

  return (
    <div className={styles.page}>
      <header className={styles.intro}>
        <p className={styles.eyebrow}>Before you arrive</p>
        <h1 className={styles.title}>Let the health centre get ready for you</h1>
        <p className={styles.lede}>Two quick steps, about two minutes. Everything you send goes with the patient, so nobody asks twice.</p>
      </header>

      {emergency && (
        <p className={styles.emergency}>
          <Phone size={18} className="shrink-0" />
          <span>
            Emergency? Call <strong className="tnum">{emergency}</strong> first. This doesn&apos;t replace it.
          </span>
        </p>
      )}

      <ol className={styles.preview}>
        <li>
          <span>1</span>Film the patient and say what happened: Presage reads heart and breathing rate
        </li>
        <li>
          <span>2</span>Take a photo of their ID, if you have it
        </li>
      </ol>

      {linked && !changing ? (
        <p className={styles.going}>
          <span>
            Going to <strong>{meta?.region.facilities.find((f) => f.id === centre)?.name}</strong>
          </span>
          <button type="button" className={styles.link} onClick={() => setChanging(true)}>
            Change
          </button>
        </p>
      ) : (
        <label className={field.field}>
          <span className={field.label}>Where are you taking them?</span>
          <select className={field.select} value={centre} onChange={(e) => setPicked(e.target.value)}>
            <option value="">Choose a health centre</option>
            {places.map((f) => (
              <option key={f.id} value={f.id}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
      )}

      <label className={styles.consent}>
        <input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} />
        <span>The patient agrees to be filmed, or can&apos;t be asked and this is for their care.</span>
      </label>

      <ButtonPrimary size="lg" className="w-full" onClick={start} disabled={!centre || !consent || busy}>
        {busy ? <Loader2 size={18} className="animate-spin" /> : null} Start <ArrowRight size={18} />
      </ButtonPrimary>
      <p className={styles.fine}>
        The camera&apos;s picture goes to our server while you measure: Presage reads heart and breathing rate from it, and Google&apos;s
        Gemini checks still frames for visible signs. The video isn&apos;t stored; only frames that show a sign are kept, for the
        hospital. The health centre sees nothing until you press Send.
      </p>
    </div>
  );
}
