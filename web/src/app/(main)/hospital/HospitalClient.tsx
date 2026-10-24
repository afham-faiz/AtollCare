// Receiving hospital: incoming handoffs on the left, the selected patient on the right.
"use client";

import { Inbox, MessageCircleQuestion } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import ModeIcon from "@/app/components/(transfer)/ModeIcon";
import Skeleton from "@/app/components/Skeleton";
import type { TransferListItem } from "@/lib/api";
import { news2Level, patientTitle } from "@/lib/clinical";
import { fmtMin, minutesUntil, place } from "@/lib/format";
import { useMeta, useTransfers } from "@/lib/swr";
import { toast } from "@/lib/toast";

import styles from "./Hospital.module.scss";
import TransferDetail from "./TransferDetail";

function Row({ t, selected, fresh, now, origin }: { t: TransferListItem; selected: boolean; fresh: boolean; now?: string; origin: string }) {
  const left = minutesUntil(t.eta, now);
  const level = news2Level(t.news2_total);
  return (
    <Link href={`/hospital/${t.id}`} className={twMerge(styles.row, selected && styles.rowSelected, fresh && styles.rowFresh)}>
      <span className={twMerge(styles.rowRule, level === "urgent" && styles.ruleUrgent, level === "watch" && styles.ruleWatch)} aria-hidden />
      <span className="min-w-0 flex-1">
        <span className="flex items-baseline justify-between gap-[.75rem]">
          <span className="truncate font-[600]">{t.suspected_condition ?? t.complaint}</span>
          <span className="tnum shrink-0 text-[0.9375rem] font-[600]">{t.status === "arrived" ? "Arrived" : left !== null ? fmtMin(left) : "—"}</span>
        </span>
        <span className="mt-[.125rem] flex items-center gap-[.375rem] truncate text-[0.875rem] text-ink-2">
          {patientTitle(t.patient)} · <ModeIcon mode={t.mode} size={14} className="shrink-0 text-ink-3" /> {origin}
        </span>
        <span className="mt-[.375rem] flex items-center gap-[.5rem] text-[0.8125rem]">
          <span className={twMerge("tnum font-[600]", level === "urgent" ? "text-critical" : level === "watch" ? "text-caution" : "text-ink-2")}>
            NEWS2 {t.news2_total ?? "—"}
          </span>
          <span className="text-ink-3">·</span>
          <span className={t.status === "pending" ? "font-[600] text-accent-strong" : "text-ink-2"}>
            {t.status === "pending" ? "Needs response" : t.status === "accepted" ? "Accepted" : "Arrived"}
          </span>
          {t.unanswered_questions > 0 && (
            <span className="ml-auto flex items-center gap-[.25rem] text-ink-3" title="Waiting for the crew to answer">
              <MessageCircleQuestion size={14} /> {t.unanswered_questions}
            </span>
          )}
        </span>
      </span>
    </Link>
  );
}

export default function ({ transferId }: { transferId?: string }) {
  const { data: meta } = useMeta();
  const { data: list } = useTransfers("pending,accepted,arrived");
  const items = list ?? [];
  const selected = transferId ?? items[0]?.id;

  // announce handoffs that arrive while the screen is open
  const known = useRef<Set<string> | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  useEffect(() => {
    if (!list) return;
    if (known.current === null) {
      known.current = new Set(list.map((t) => t.id));
      return;
    }
    const arrivals = list.filter((t) => !known.current!.has(t.id));
    if (!arrivals.length) return;
    arrivals.forEach((t) => known.current!.add(t.id));
    // highlight briefly, then settle
    setFresh(new Set(arrivals.map((t) => t.id)));
    toast(`New handoff · ${arrivals.map((t) => t.suspected_condition ?? t.code).join(", ")}`);
    const timer = window.setTimeout(() => setFresh(new Set()), 4000);
    return () => window.clearTimeout(timer);
  }, [list]);

  return (
    <div className={styles.layout}>
      <aside className={styles.rail} aria-label="Incoming transfers">
        <h1 className={styles.railTitle}>
          Incoming <span className="tnum text-ink-3">{items.length || ""}</span>
        </h1>
        {!list && <Skeleton className="h-[5.5rem] rounded-[1.25rem]" />}
        {list && items.length === 0 && (
          <div className={styles.empty}>
            <Inbox size={22} className="text-ink-3" />
            <p className="font-[600]">No incoming transfers</p>
            <p className="text-[0.875rem] text-ink-2">Handoffs appear here the moment a crew sends them.</p>
          </div>
        )}
        {items.length > 0 && (
          <nav className={styles.list}>
            {items.map((t) => (
              <Row
                key={t.id}
                t={t}
                selected={selected === t.id}
                fresh={fresh.has(t.id)}
                now={meta?.now}
                origin={place(meta?.regions.find((r) => r.id === t.region_id), t.origin_id)}
              />
            ))}
          </nav>
        )}
      </aside>
      <section className="min-w-0">{selected ? <TransferDetail transferId={selected} key={selected} /> : null}</section>
    </div>
  );
}
