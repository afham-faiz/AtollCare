// Receiving hospital: incoming handoffs on the left, the selected patient on the right.
"use client";

import { Inbox, MessageCircleQuestion } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import Skeleton from "@/app/components/Skeleton";
import type { TransferListItem } from "@/lib/api";
import { news2Level, patientTitle } from "@/lib/clinical";
import { fmtTime, minutesUntil, place } from "@/lib/format";
import { useMeta, useTransfers } from "@/lib/swr";
import { toast } from "@/lib/toast";

import styles from "./Hospital.module.scss";
import TransferDetail from "./TransferDetail";

// minutes to arrival as a numeral: "42" min, or "1:16" h
function Countdown({ minutes }: { minutes: number }) {
  const total = Math.max(0, Math.round(minutes));
  const h = Math.floor(total / 60);
  const m = total % 60;
  return h ? (
    <>
      <span className="numeral">{h}</span>
      <span className="unit">h</span>
      <span className="numeral">{String(m).padStart(2, "0")}</span>
    </>
  ) : (
    <>
      <span className="numeral">{total}</span>
      <span className="unit">min</span>
    </>
  );
}

function Row({ t, selected, fresh, now, origin, tz }: { t: TransferListItem; selected: boolean; fresh: boolean; now?: string; origin: string; tz?: string }) {
  const left = minutesUntil(t.eta, now);
  const level = news2Level(t.news2_total);
  // the open patient is always in view, even far down the list
  const ref = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    const row = ref.current;
    const rail = row?.closest("aside");
    // scroll the list only (never the page), and only where the list scrolls on its own (laptops)
    if (!selected || !row || !rail || rail.scrollHeight <= rail.clientHeight) return;
    const top = row.getBoundingClientRect().top - rail.getBoundingClientRect().top + rail.scrollTop;
    rail.scrollTop = top - rail.clientHeight / 2 + row.offsetHeight / 2;
  }, [selected]);
  return (
    <Link
      ref={ref}
      href={`/hospital/${t.id}`}
      className={twMerge(styles.row, selected && styles.rowSelected, fresh && styles.rowFresh)}
      aria-current={selected ? "page" : undefined}
    >
      <span className={styles.rowMain}>
        <span className={styles.rowTitle}>{t.suspected_condition ?? t.complaint}</span>
        <span className={styles.rowMeta}>
          {patientTitle(t.patient)} · {origin}
        </span>
        {(level !== null || t.status === "pending" || t.unanswered_questions > 0) && (
          <span className={styles.rowFoot}>
            {level !== null && (
              <span className={twMerge(styles.news, styles[level])}>
                <span className={styles.newsDot} aria-hidden />
                <span className="tnum">NEWS2 {t.news2_total}</span>
              </span>
            )}
            {t.status === "pending" && <span className={styles.needs}>Needs response</span>}
            {t.unanswered_questions > 0 && (
              <span className={styles.asked} title="Waiting for the crew to answer">
                <MessageCircleQuestion size={14} strokeWidth={1.75} /> {t.unanswered_questions}
              </span>
            )}
          </span>
        )}
      </span>
      <span className={styles.rowEta}>{t.status === "arrived" ? <span className={twMerge("tnum", styles.rowArrived)}>{fmtTime(t.eta, tz)}</span> : left !== null ? <Countdown minutes={left} /> : null}</span>
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
        {!list && <Skeleton className="h-[5.5rem] rounded-[1.75rem]" />}
        {list && items.length === 0 && (
          <div className={twMerge("card", styles.empty)}>
            <Inbox size={22} strokeWidth={1.75} className="text-ink-3" />
            <p className="font-[500]">No incoming transfers</p>
            <p className="text-[0.875rem] text-ink-3">Handoffs appear here the moment a crew sends them.</p>
          </div>
        )}
        {[
          { title: "Incoming", rows: items.filter((t) => t.status !== "arrived") },
          { title: "Arrived", rows: items.filter((t) => t.status === "arrived") },
        ]
          .filter((g) => g.rows.length > 0)
          .map((g) => (
            <section key={g.title} className={styles.group}>
              <h1 className={styles.railTitle}>
                {g.title} <span className="tnum text-ink-3">{g.rows.length}</span>
              </h1>
              <nav className={styles.list}>
                {g.rows.map((t) => (
                  <Row
                    key={t.id}
                    t={t}
                    selected={selected === t.id}
                    fresh={fresh.has(t.id)}
                    now={meta?.now}
                    origin={place(meta?.regions.find((r) => r.id === t.region_id), t.origin_id)}
                    tz={meta?.regions.find((r) => r.id === t.region_id)?.timezone}
                  />
                ))}
              </nav>
            </section>
          ))}
      </aside>
      <section className="min-w-0">{selected ? <TransferDetail transferId={selected} key={selected} /> : null}</section>
    </div>
  );
}
