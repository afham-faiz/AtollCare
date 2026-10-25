// Receiving hospital: incoming handoffs on the left, the selected patient on the right.
// Phones show one at a time: the inbox, or the patient with a way back to it.
"use client";

import { ChevronLeft, Inbox, MessageCircleQuestion, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";

import Segmented from "@/app/components/(controls)/Segmented";
import Skeleton from "@/app/components/Skeleton";
import type { TransferListItem } from "@/lib/api";
import { news2Level, patientTitle } from "@/lib/clinical";
import { fmtTime, minutesUntil, place, sentence } from "@/lib/format";
import { activeFilters, inbox, NO_FILTERS, type InboxFilters, type Severity, type Sort, type Within } from "@/lib/inbox";
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
        <span className={styles.rowTitle}>{sentence(t.suspected_condition ?? t.complaint)}</span>
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

const ARRIVED_PREVIEW = 3;

export default function ({ transferId }: { transferId?: string }) {
  const { data: meta } = useMeta();
  const { data: list } = useTransfers("pending,accepted,arrived");
  const items = list ?? [];
  const [filters, setFilters] = useState<InboxFilters>(NO_FILTERS);
  const [filtering, setFiltering] = useState(false);
  const set = (next: Partial<InboxFilters>) => setFilters((f) => ({ ...f, ...next }));
  const shown = inbox(items, filters, meta?.now);
  const waiting = items.filter((t) => t.status === "pending").length;
  const narrowing = activeFilters(filters);
  const selected = transferId ?? shown.incoming[0]?.id ?? items[0]?.id;
  // the arrived pile grows all shift: the latest few, unless asked (or the open patient is further down)
  const [allArrived, setAllArrived] = useState(false);
  const openIndex = shown.arrived.findIndex((t) => t.id === selected);
  const arrivedRows = allArrived || openIndex >= ARRIVED_PREVIEW ? shown.arrived : shown.arrived.slice(0, ARRIVED_PREVIEW);

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
    <div className={twMerge(styles.layout, transferId && styles.picked)}>
      <aside className={styles.rail} aria-label="Incoming transfers">
        {list && items.length > 0 && (
          <div className={styles.filters}>
            <div className={styles.filterRow}>
              <button
                type="button"
                className={twMerge(styles.chip, filters.needsResponse && styles.chipOn)}
                aria-pressed={filters.needsResponse}
                onClick={() => set({ needsResponse: !filters.needsResponse })}
              >
                Needs response <span className={twMerge("tnum", styles.chipCount)}>{waiting}</span>
              </button>
              <button type="button" className={twMerge(styles.chip, filtering && styles.chipOn)} aria-expanded={filtering} onClick={() => setFiltering((v) => !v)}>
                <SlidersHorizontal size={15} strokeWidth={1.75} /> Filter
                {narrowing > (filters.needsResponse ? 1 : 0) && <span className={twMerge("tnum", styles.chipCount)}>{narrowing - (filters.needsResponse ? 1 : 0)}</span>}
              </button>
              {narrowing > 0 && (
                <button type="button" className={styles.clear} onClick={() => setFilters({ ...NO_FILTERS, sort: filters.sort })} aria-label="Clear filters" title="Clear filters">
                  <X size={15} strokeWidth={1.75} />
                </button>
              )}
            </div>
            {filtering && (
              <div className={twMerge("card", styles.filterPanel)}>
                <div className={styles.filterGroup}>
                  <span className={styles.filterLabel}>Order</span>
                  <Segmented<Sort>
                    label="Order"
                    size="sm"
                    className="w-full"
                    value={filters.sort}
                    onChange={(sort) => set({ sort })}
                    options={[
                      { value: "eta", label: "Arriving soonest" },
                      { value: "severity", label: "Most urgent" },
                    ]}
                  />
                </div>
                <div className={styles.filterGroup}>
                  <span className={styles.filterLabel}>Severity</span>
                  <Segmented<Severity>
                    label="Severity"
                    size="sm"
                    className="w-full"
                    value={filters.severity}
                    onChange={(severity) => set({ severity })}
                    options={[
                      { value: "any", label: "Any" },
                      { value: "high", label: "High" },
                      { value: "medium", label: "Medium" },
                      { value: "low", label: "Low" },
                    ]}
                  />
                </div>
                <div className={styles.filterGroup}>
                  <span className={styles.filterLabel}>Arriving within</span>
                  <Segmented<Within>
                    label="Arriving within"
                    size="sm"
                    className="w-full"
                    value={filters.within}
                    onChange={(within) => set({ within })}
                    options={[
                      { value: "any", label: "Any time" },
                      { value: "30", label: "30 min" },
                      { value: "60", label: "1 h" },
                      { value: "120", label: "2 h" },
                    ]}
                  />
                </div>
              </div>
            )}
          </div>
        )}
        {!list && <Skeleton className="h-[5.5rem] rounded-[1.75rem]" />}
        {list && items.length === 0 && (
          <div className={twMerge("card", styles.empty)}>
            <Inbox size={22} strokeWidth={1.75} className="text-ink-3" />
            <p className="font-[500]">No incoming transfers</p>
            <p className="text-[0.875rem] text-ink-3">Handoffs appear here the moment a crew sends them.</p>
          </div>
        )}
        {list && items.length > 0 && !shown.incoming.length && !shown.arrived.length && (
          <div className={twMerge("card", styles.empty)}>
            <p className="font-[500]">Nothing matches these filters</p>
            <button type="button" className="text-[0.875rem] font-[500] text-accent" onClick={() => setFilters({ ...NO_FILTERS, sort: filters.sort })}>
              Clear filters
            </button>
          </div>
        )}
        {[
          { title: filters.needsResponse ? "Needs response" : "Incoming", rows: shown.incoming, visible: shown.incoming, folds: false },
          { title: "Arrived", rows: shown.arrived, visible: arrivedRows, folds: true },
        ]
          .filter((g) => g.rows.length > 0)
          .map((g) => (
            <section key={g.title} className={styles.group}>
              <h1 className={styles.railTitle}>
                {g.title} <span className="tnum text-ink-3">{g.rows.length}</span>
              </h1>
              <nav className={styles.list}>
                {g.visible.map((t) => (
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
              {g.folds && g.rows.length > ARRIVED_PREVIEW && (
                <button type="button" className={styles.more} onClick={() => setAllArrived((v) => !v)} disabled={openIndex >= ARRIVED_PREVIEW}>
                  {g.visible.length < g.rows.length ? `Show all ${g.rows.length}` : "Show fewer"}
                </button>
              )}
            </section>
          ))}
      </aside>
      <section className={twMerge("min-w-0", styles.detail)}>
        <Link href="/hospital" className={styles.back}>
          <ChevronLeft size={18} strokeWidth={1.75} /> All transfers
        </Link>
        {selected ? <TransferDetail transferId={selected} key={selected} /> : null}
      </section>
    </div>
  );
}
