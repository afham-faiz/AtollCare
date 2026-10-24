// F-M2.10 Engine inspector drawer: NEWS2 components, condition probabilities, every route (incl. infeasible with
// reasons), score breakdown, Gemini vs fallback badges, input hash.
"use client";

import { ChevronDown, Cpu } from "lucide-react";
import { useState } from "react";
import { twMerge } from "tailwind-merge";

import Card from "@/app/components/Card";
import SourceBadge from "@/app/components/SourceBadge";
import type { Case, Facility } from "@/lib/api";
import { CONDITION_LABEL, facilityName, fmtMin } from "@/lib/format";
import { useRoutes } from "@/lib/swr";

export default function ({ c, facilities, className }: { c: Case; facilities?: Facility[]; className?: string }) {
  const [open, setOpen] = useState(false);
  const { data: routes } = useRoutes(c.id, open);
  const rec = c.recommendation;
  return (
    <Card className={className}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex min-h-[2.75rem] w-full items-center gap-[.5rem] text-left font-semibold"
        aria-expanded={open}
      >
        <Cpu size={20} className="text-brand" /> Engine details
        <ChevronDown size={16} className={twMerge("ml-auto transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="mt-[.75rem] flex flex-col gap-[1rem] text-[0.875rem]">
          <div className="flex flex-wrap gap-[.375rem]">
            {c.intake && <SourceBadge kind={c.intake.extracted_by === "gemini" ? "gemini" : "fallback"} title="Intake" />}
            {rec && <SourceBadge kind={rec.explanation_source === "gemini" ? "gemini" : "template"} title="Explanation" />}
            {rec && <span className="text-muted">engine v{rec.engine_version} · hash {rec.input_hash}</span>}
          </div>
          <section>
            <h3 className="mb-[.25rem] font-semibold">NEWS2 components</h3>
            {c.news2 ? (
              <p className="tabular-nums">
                {Object.entries(c.news2.components)
                  .map(([k, v]) => `${k}=${v ?? "–"}`)
                  .join(" · ")}{" "}
                → total {c.news2.total} ({c.news2.band}){c.news2.complete ? "" : `, missing ${c.news2.missing.join(", ")}`}
              </p>
            ) : (
              <p className="text-muted">No vitals.</p>
            )}
          </section>
          <section>
            <h3 className="mb-[.25rem] font-semibold">Condition probabilities</h3>
            {rec?.condition_probabilities.length ? (
              <ul>
                {rec.condition_probabilities.map((s) => (
                  <li key={s.condition_id}>
                    {CONDITION_LABEL[s.condition_id] ?? s.condition_id}: {(s.probability * 100).toFixed(0)}% — {s.rationale}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-muted">No intake yet.</p>
            )}
            {rec && (
              <p className="mt-[.25rem] text-muted">
                Required capabilities: {rec.required_capabilities.join(", ")} · window {rec.window_min ?? "none"} min
                {rec.interim_window_min ? ` · interim window ${rec.interim_window_min} min` : ""}
              </p>
            )}
          </section>
          <section>
            <h3 className="mb-[.25rem] font-semibold">All routes ({routes?.length ?? rec?.all_routes_count ?? 0})</h3>
            {!routes && <p className="text-muted">Loading routes…</p>}
            <div className="overflow-x-auto">
              <table className="w-full min-w-[40rem] text-[0.875rem] tabular-nums">
                <thead className="text-left text-muted">
                  <tr>
                    <th className="py-[.25rem] pr-[.5rem]">Route</th>
                    <th className="pr-[.5rem]">To</th>
                    <th className="pr-[.5rem]">Total</th>
                    <th className="pr-[.5rem]">Score</th>
                    <th>Breakdown / reasons</th>
                  </tr>
                </thead>
                <tbody>
                  {routes?.map((r) => (
                    <tr
                      key={r.id}
                      className={twMerge(
                        "border-t-[1px] border-border align-top",
                        r.id === rec?.chosen_route_id && "bg-brand-soft",
                        !r.feasible && "text-muted",
                      )}
                    >
                      <td className="py-[.25rem] pr-[.5rem]">{r.label}</td>
                      <td className="pr-[.5rem]">{facilityName(facilities, r.destination_id)}</td>
                      <td className="pr-[.5rem]">{fmtMin(r.total_min)}</td>
                      <td className="pr-[.5rem]">{r.score}</td>
                      <td>
                        {r.feasible ? (
                          Object.entries(r.score_breakdown)
                            .map(([k, v]) => `${k} ${v > 0 ? "+" : ""}${v}`)
                            .join(", ")
                        ) : (
                          <span className="text-alert">{r.infeasible_reasons.join("; ")}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </div>
      )}
    </Card>
  );
}
