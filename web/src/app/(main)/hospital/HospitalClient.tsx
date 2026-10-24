// Hospital screen: incoming transfers on the left, the selected transfer on the right.
"use client";

import { Inbox } from "lucide-react";
import Link from "next/link";
import { twMerge } from "tailwind-merge";

import ModeIcon from "@/app/components/(transfer)/ModeIcon";
import StatusPill from "@/app/components/(transfer)/StatusPill";
import Skeleton from "@/app/components/Skeleton";
import { fmtMin, minutesUntil, patientLine, place } from "@/lib/format";
import { useMeta, useTransfers } from "@/lib/swr";

import TransferDetail from "./TransferDetail";

export default function ({ transferId }: { transferId?: string }) {
  const { data: meta } = useMeta();
  const { data: list } = useTransfers();
  const items = (list ?? []).filter((t) => t.status !== "closed");
  const selected = transferId ?? (items.length === 1 ? items[0].id : undefined);

  return (
    <div className="grid gap-[1rem] lg:grid-cols-[20rem_1fr]">
      <aside className="flex flex-col gap-[.5rem]">
        <h1 className="px-[.25rem] text-[0.875rem] font-semibold text-muted">Incoming ({items.length})</h1>
        {!list && <Skeleton className="h-[6rem]" />}
        {list && items.length === 0 && (
          <div className="rounded-[.75rem] border-[1px] border-dashed border-border p-[1.25rem] text-center text-muted">
            <Inbox size={28} className="mx-auto mb-[.5rem]" />
            No incoming transfers.
            <br />
            <Link href="/crew" className="text-brand-strong underline">Start one on the crew screen</Link>
          </div>
        )}
        {items.map((t) => {
          const left = minutesUntil(t.eta, meta?.now);
          const tone = t.alert_level === "critical" ? "bg-alert" : t.alert_level === "warning" ? "bg-warn" : "bg-brand";
          return (
            <Link
              key={t.id}
              href={`/hospital/${t.id}`}
              className={twMerge(
                "relative flex flex-col gap-[.375rem] overflow-hidden rounded-[.75rem] border-[1px] border-border bg-surface p-[.875rem] pl-[1.125rem] hover:border-brand",
                selected === t.id && "border-brand ring-[.125rem] ring-brand/20",
              )}
            >
              <span className={twMerge("absolute inset-y-0 left-0 w-[.25rem]", tone)} aria-hidden />
              <span className="flex items-center justify-between gap-[.5rem]">
                <strong className="tabular-nums">{t.code}</strong>
                <span className="text-[0.9375rem] font-semibold tabular-nums">
                  {t.status === "arrived" ? "Arrived" : left !== null ? fmtMin(left) : "—"}
                </span>
              </span>
              <span className="truncate text-[0.9375rem]">
                {patientLine(t.patient)} · {t.suspected_condition ?? t.complaint}
              </span>
              <span className="flex items-center justify-between gap-[.5rem] text-[0.875rem] text-muted">
                <span className="flex min-w-0 items-center gap-[.375rem] truncate">
                  <ModeIcon mode={t.mode} /> {place(meta?.regions.find((r) => r.id === t.region_id), t.origin_id)}
                </span>
                <span className="tabular-nums">NEWS2 {t.news2_total ?? "—"}</span>
              </span>
              <span className="flex items-center gap-[.5rem]">
                <StatusPill status={t.status} />
                {t.unanswered_questions > 0 && (
                  <span className="text-[0.875rem] text-info">Waiting for crew answer</span>
                )}
              </span>
            </Link>
          );
        })}
      </aside>

      <section className="min-w-0">
        {selected ? (
          <TransferDetail transferId={selected} />
        ) : (
          items.length > 0 && (
            <div className="flex h-[20rem] items-center justify-center rounded-[.75rem] border-[1px] border-dashed border-border text-muted">
              Select a transfer
            </div>
          )
        )}
      </section>
    </div>
  );
}
