// Pre-arrival, first screen (the companion's phone): where are you taking them? Then the three steps.
"use client";

import { ArrowRight, Loader2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import { post, type Intake } from "@/lib/api";
import { useMeta } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./PreArrival.module.scss";

export default function () {
  const router = useRouter();
  const { data: meta } = useMeta();
  const [centre, setCentre] = useState("");
  const [busy, setBusy] = useState(false);
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
        <p className={styles.lede}>Three quick steps, about three minutes. Everything you send goes with the patient, so nobody asks twice.</p>
      </header>

      <ol className={styles.preview}>
        <li>
          <span>1</span>Point your phone at the patient: Presage reads heart and breathing rate
        </li>
        <li>
          <span>2</span>Say what happened, in your own words
        </li>
        <li>
          <span>3</span>Take a photo of their ID, if you have it
        </li>
      </ol>

      <label className={field.field}>
        <span className={field.label}>Where are you taking them?</span>
        <select className={field.select} value={centre} onChange={(e) => setCentre(e.target.value)}>
          <option value="">Choose a health centre</option>
          {places.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
      </label>

      <ButtonPrimary size="lg" className="w-full" onClick={start} disabled={!centre || busy}>
        {busy ? <Loader2 size={18} className="animate-spin" /> : null} Start <ArrowRight size={18} />
      </ButtonPrimary>
      <p className={styles.fine}>
        The video is analysed as soon as you record it, but the health centre sees nothing until you press Send. The video itself
        isn&apos;t kept — only the measurements and the few frames they rely on.
      </p>
    </div>
  );
}
