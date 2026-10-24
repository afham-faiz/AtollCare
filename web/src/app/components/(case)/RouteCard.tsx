// F-M1.5 / F-M2.5 / F-M2.8 Recommended route: legs, ETA, window margin, breach warning, explanation, alternatives.
"use client";

import { AlertTriangle, ChevronDown } from "lucide-react";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

import Card from "@/app/components/Card";
import SourceBadge from "@/app/components/SourceBadge";
import PillSeverity from "@/app/components/(pills)/PillSeverity";
import type { Facility, Recommendation, RouteOption } from "@/lib/api";
import { CONDITION_LABEL, MODE_LABEL, facilityName, fmtMin, fmtTime } from "@/lib/format";

import ModeIcon from "./ModeIcon";

export function RouteLegs({ route, facilities }: { route: RouteOption; facilities?: Facility[] }) {
  if (!route.legs.length) return <p className="text-[0.875rem] text-muted">{route.label}</p>;
  return (
    <ol className="flex flex-col gap-[.375rem]">
      {route.legs.map((leg, i) => (
        <li key={i} className="flex items-center gap-[.5rem] text-[0.875rem]">
          <ModeIcon mode={leg.mode} className="shrink-0 text-brand" />
          <span className="min-w-0 flex-1 truncate">
            {MODE_LABEL[leg.mode]} → {facilityName(facilities, leg.to_id)}
            {route.interim_stop_id === leg.to_id && <span className="ml-[.25rem] font-semibold text-warn-fg">· interim</span>}
          </span>
          <span className="shrink-0 tabular-nums text-muted">
            {fmtTime(leg.depart_at)}–{fmtTime(leg.arrive_at)}
          </span>
        </li>
      ))}
    </ol>
  );
}

function Margin({ route }: { route: RouteOption }) {
  if (route.window_margin_min === null || route.window_margin_min === undefined) return null;
  const ok = route.window_margin_min >= 0;
  return (
    <span className={twMerge("tabular-nums", ok ? "text-brand" : "text-alert")}>
      {ok ? `${fmtMin(route.window_margin_min)} inside window` : `${fmtMin(-route.window_margin_min)} over window`}
    </span>
  );
}

export default function ({
  rec,
  facilities,
  className,
  compact = false,
}: {
  rec: Recommendation;
  facilities?: Facility[];
  className?: string;
  compact?: boolean;
}) {
  const [showAlt, setShowAlt] = useState(false);
  const chosen = rec.alternatives.find((r) => r.id === rec.chosen_route_id) ?? rec.alternatives[0];
  const others = rec.alternatives.filter((r) => r.id !== chosen?.id);
  return (
    <Card
      title="Recommended route"
      className={className}
      aside={
        <span className="flex items-center gap-[.375rem]">
          <PillSeverity severity={rec.severity} />
        </span>
      }
    >
      <div className="flex flex-wrap items-baseline gap-x-[1rem] gap-y-[.25rem]">
        <span className="text-[2.25rem] font-bold leading-none tabular-nums">{fmtMin(chosen?.total_min)}</span>
        <span className="text-[0.9375rem]">
          to <strong>{facilityName(facilities, rec.destination_id)}</strong> · ETA {fmtTime(chosen?.arrive_at)}
        </span>
      </div>
      <p className="mt-[.25rem] text-[0.875rem] text-muted">
        {CONDITION_LABEL[rec.primary_condition_id ?? "other"] ?? rec.primary_condition_id}
        {rec.window_min ? ` · window ${fmtMin(rec.window_min)}` : ""}
        {rec.time_since_onset_min !== null && rec.time_since_onset_min !== undefined
          ? ` · ${fmtMin(rec.time_since_onset_min)} since ${rec.onset_confidence === "unknown" ? "alert" : "onset"}`
          : ""}
        {chosen && (
          <>
            {" · "}
            <Margin route={chosen} />
          </>
        )}
      </p>
      {rec.onset_confidence === "unknown" && rec.window_min && (
        <p className="mt-[.25rem] text-[0.875rem] text-warn-fg">Onset time unknown — window counted from the alert.</p>
      )}
      {rec.breach_warning && (
        <div className="mt-[.75rem] flex gap-[.5rem] rounded-[.5rem] border-[1px] border-alert bg-alert-soft p-[.75rem] text-[0.875rem]">
          <AlertTriangle size={20} className="shrink-0 text-alert" />
          <p>{rec.breach_warning}</p>
        </div>
      )}
      {rec.warnings.map((w) => (
        <p key={w} className="mt-[.5rem] rounded-[.5rem] bg-warn-soft p-[.5rem] text-[0.875rem] text-warn-fg">
          {w}
        </p>
      ))}
      {chosen && (
        <div className="mt-[.75rem]">
          <RouteLegs route={chosen} facilities={facilities} />
        </div>
      )}
      <div className="mt-[.75rem] rounded-[.5rem] bg-surface p-[.75rem]">
        <p className="text-[0.875rem]">{rec.explanation}</p>
        <div className="mt-[.5rem] flex flex-wrap gap-[.375rem]">
          <SourceBadge kind={rec.explanation_source === "gemini" ? "gemini" : "template"} />
          <SourceBadge kind="assumption" title="Transport speeds, windows and capabilities are illustrative" />
        </div>
      </div>
      {!compact && others.length > 0 && (
        <div className="mt-[.75rem]">
          <button
            type="button"
            onClick={() => setShowAlt((s) => !s)}
            className="flex min-h-[2.75rem] items-center gap-[.25rem] text-[0.875rem] font-medium text-brand"
          >
            <ChevronDown size={16} className={twMerge("transition-transform", showAlt && "rotate-180")} />
            {showAlt ? "Hide" : "Show"} {others.length} alternative{others.length > 1 ? "s" : ""}
          </button>
          {showAlt && (
            <ul className="flex flex-col gap-[.5rem]">
              {others.map((r) => (
                <li key={r.id} className="rounded-[.5rem] border-[1px] border-border p-[.75rem]">
                  <div className="flex flex-wrap items-baseline justify-between gap-[.5rem]">
                    <span className="text-[0.875rem] font-medium">{r.label}</span>
                    <span className="tabular-nums text-[0.875rem]">{fmtMin(r.total_min)}</span>
                  </div>
                  <p className="text-[0.875rem] text-muted">
                    {facilityName(facilities, r.destination_id)} · score {r.score} · <Margin route={r} />
                  </p>
                  {!r.feasible && (
                    <p className="mt-[.25rem] text-[0.875rem] text-alert">{r.infeasible_reasons.join("; ")}</p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Card>
  );
}
