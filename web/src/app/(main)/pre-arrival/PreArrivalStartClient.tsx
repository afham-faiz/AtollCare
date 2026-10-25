// Pre-arrival, first screen (the companion's phone): the emergency number first, where they're going, what happens,
// and one button. Pressing it is the consent; the details of what happens to the video are one tap away.
"use client";

import { ArrowRight, Loader2, Phone } from "lucide-react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import field from "@/app/components/(controls)/Field.module.scss";
import Sheet from "@/app/components/(modals)/Sheet";
import { post, type Intake } from "@/lib/api";
import { splitPlace } from "@/lib/format";
import { useMeta } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./PreArrival.module.scss";

export default function ({ centre: fromLink }: { centre?: string }) {
  const router = useRouter();
  const { data: meta } = useMeta();
  const [picked, setPicked] = useState("");
  const [changing, setChanging] = useState(false);
  const [privacy, setPrivacy] = useState(false);
  const [busy, setBusy] = useState(false);
  const emergency = meta?.region.emergency_number;
  const linked = meta?.region.facilities.find((f) => f.id === fromLink);
  const centre = picked || linked?.id || "";
  const chosen = meta?.region.facilities.find((f) => f.id === centre);
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

  const where = chosen ? splitPlace(chosen.name) : null;

  return (
    <div className={styles.page}>
      {emergency && (
        <a className={styles.call} href={`tel:${emergency}`}>
          <Phone size={16} strokeWidth={1.75} />
          <span>
            Emergency? Call <strong className="tnum">{emergency}</strong> first
          </span>
        </a>
      )}

      <header className={styles.hero}>
        <h1 className={styles.display}>Let the health centre get ready before you arrive</h1>
        <p className={styles.lede}>Two minutes on this phone. It all goes with the patient, so nobody asks twice.</p>
      </header>

      {where && !changing ? (
        <button type="button" className={styles.destination} onClick={() => setChanging(true)}>
          <span className={styles.destinationLabel}>Going to</span>
          <span className={styles.destinationName}>{where.name}</span>
          {where.area && <span className={styles.destinationArea}>{where.area}</span>}
          <span className={styles.destinationChange}>Change</span>
        </button>
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

      <ol className={styles.plan}>
        <li>
          <span className={styles.planNo}>1</span>
          <span>
            <strong>Film them for 30 seconds</strong>
            Heart and breathing rate, measured by Presage without touching
          </span>
        </li>
        <li>
          <span className={styles.planNo}>2</span>
          <span>
            <strong>Say what happened</strong>
            While you film, or after
          </span>
        </li>
        <li>
          <span className={styles.planNo}>3</span>
          <span>
            <strong>Their ID</strong>
            If you have it
          </span>
        </li>
      </ol>

      <div className={styles.go}>
        <p className={styles.consentLine}>Starting means the patient agrees to be filmed, or can&apos;t be asked and it&apos;s for their care.</p>
        <ButtonPrimary size="lg" className="w-full" onClick={start} disabled={!centre || busy}>
          {busy ? <Loader2 size={18} strokeWidth={1.75} className="animate-spin" /> : null} {centre ? "Start filming" : "Choose where you're going"} {centre && !busy && <ArrowRight size={18} strokeWidth={1.75} />}
        </ButtonPrimary>
        <button type="button" className={styles.quietLink} onClick={() => setPrivacy(true)}>
          How the video is used
        </button>
      </div>

      <Sheet open={privacy} onClose={() => setPrivacy(false)} title="How the video is used">
        <div className={styles.privacy}>
          <p>While you film, the picture goes to our server so Presage can measure heart and breathing rate from it.</p>
          <p>Google&apos;s Gemini looks at still frames for visible signs, like a drooping face.</p>
          <p>The video itself isn&apos;t kept. Only frames that show a sign are saved, for the hospital.</p>
          <p>The health centre sees nothing until you press Send.</p>
        </div>
      </Sheet>
    </div>
  );
}
