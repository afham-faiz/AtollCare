// Landing: one sentence, two screens, three steps.
"use client";

import { ArrowRight, Building2, Camera, Mic, Sparkles, Video } from "lucide-react";
import Link from "next/link";

import { APP_TAGLINE, SPONSORS } from "@/app/config";
import { useMeta } from "@/lib/swr";

import styles from "./Landing.module.scss";

const STEPS = [
  { Icon: Camera, title: "Hands-free vitals", text: "A mounted camera reads heart rate, breathing and HRV with Presage while the crew keeps working." },
  { Icon: Mic, title: "Talk, don't type", text: "Crew speak notes. Interventions are picked out and added to the record." },
  { Icon: Sparkles, title: "Ready on arrival", text: "The hospital sees a live briefing and trend, accepts in one tap, and asks questions read aloud in the vehicle." },
];

export default function () {
  const { data: meta } = useMeta();
  return (
    <div className="mx-auto flex max-w-[64rem] flex-col gap-[2.5rem] py-[1.5rem]">
      <section>
        <h1 className="max-w-[40rem] text-[2.5rem] font-bold leading-tight">{APP_TAGLINE}</h1>
        <p className="mt-[1rem] max-w-[44rem] text-[1.125rem] text-muted">
          Emergency transfers from islands and remote communities take hours. AtollCare turns that time into
          information: the receiving team knows the patient before the doors open.
        </p>
      </section>

      <section className="grid gap-[1rem] md:grid-cols-2">
        <Link href="/crew" className={styles.door}>
          <Video size={28} className="text-brand" />
          <h2>Crew screen</h2>
          <p>Tablet or laptop mounted in the boat, ambulance or aircraft.</p>
          <span className={styles.go}>
            Open <ArrowRight size={18} />
          </span>
        </Link>
        <Link href="/hospital" className={styles.door}>
          <Building2 size={28} className="text-brand" />
          <h2>Hospital screen</h2>
          <p>Receiving team: incoming transfers, live vitals, briefing, accept.</p>
          <span className={styles.go}>
            Open <ArrowRight size={18} />
          </span>
        </Link>
      </section>

      <section className="grid gap-[1.5rem] md:grid-cols-3">
        {STEPS.map(({ Icon, title, text }) => (
          <div key={title}>
            <Icon size={22} className="mb-[.5rem] text-brand" />
            <h3 className="font-semibold">{title}</h3>
            <p className="text-muted">{text}</p>
          </div>
        ))}
      </section>

      <section className="flex flex-wrap items-center gap-x-[1.5rem] gap-y-[.5rem] border-t-[1px] border-border pt-[1.25rem] text-[0.9375rem] text-muted">
        <span>
          Works anywhere: {meta?.regions.map((r) => r.name).join(" · ") ?? "…"} · add a region as one JSON file
        </span>
        <span className="ml-auto">Built with {SPONSORS.join(" · ")}</span>
      </section>
    </div>
  );
}
