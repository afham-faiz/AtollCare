// F-M10.1 Landing: problem, headline metric from the last closed demo case, role entry cards, sponsor strip.
"use client";

import { Hospital, Ship, Siren } from "lucide-react";
import Link from "next/link";

import { APP_NAME, APP_TAGLINE, SPONSORS } from "@/app/config";
import CaseHeadline from "@/app/components/(case)/CaseHeadline";
import PillBase from "@/app/components/(pills)/PillBase";
import { setRole, type Role } from "@/lib/role";
import { useCases } from "@/lib/swr";

import styles from "./Landing.module.scss";

const ENTRIES: { href: string; role: Role; title: string; text: string; Icon: typeof Siren }[] = [
  { href: "/report", role: "reporter", title: "Island", text: "Raise an alert, scan vitals, get first-aid guidance.", Icon: Siren },
  { href: "/hospital", role: "specialist", title: "Hospital", text: "Review referrals, accept in one click, manage capacity.", Icon: Hospital },
  { href: "/transport", role: "transport", title: "Transport", text: "Dispatch the fastest feasible route and track it live.", Icon: Ship },
];

export default function () {
  const { data: closed } = useCases("?status=closed,arrived");
  const last = [...(closed ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at))[0];
  return (
    <div className="flex flex-col gap-[2rem] py-[1rem]">
      <section className="max-w-[48rem]">
        <p className="text-[0.875rem] font-semibold uppercase tracking-[0.08em] text-brand">{APP_NAME}</p>
        <h1 className="mt-[.5rem] text-[2.25rem] font-bold leading-tight">{APP_TAGLINE}</h1>
        <p className="mt-[1rem] text-[1.0625rem] text-muted">
          Across ~190 inhabited islands in the Maldives, the delay between an outer-island emergency and specialist care is
          not medicine — it is a sequential phone chain of handoffs. {APP_NAME} gives every patient one live case that
          travels with them: contactless vitals and AI-structured intake on the island, a clinically grounded engine that
          picks the fastest route to the right hospital within the treatment window, one-click acceptance in Malé, and live
          transport tracking — with every handoff happening in parallel.
        </p>
      </section>
      {last && <CaseHeadline headline={last.headline} />}
      <section className={styles.entries}>
        {ENTRIES.map(({ href, role, title, text, Icon }) => (
          <Link key={href} href={href} onClick={() => setRole(role)} className={styles.entry}>
            <Icon size={24} className="text-brand" />
            <h2>{title}</h2>
            <p>{text}</p>
          </Link>
        ))}
      </section>
      <section className="flex flex-wrap items-center gap-[.5rem]">
        <span className="text-[0.875rem] text-muted">Built with</span>
        {SPONSORS.map((s) => (
          <PillBase key={s}>{s}</PillBase>
        ))}
        <Link href="/demo" className="ml-auto text-[0.875rem] text-brand underline">
          Demo control →
        </Link>
      </section>
    </div>
  );
}
