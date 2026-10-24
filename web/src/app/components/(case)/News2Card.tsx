// F-M2.3 / F-M1.4 NEWS2 card with component breakdown and Partial badge.
import { twMerge } from "tailwind-merge";

import Card from "@/app/components/Card";
import PillBase from "@/app/components/(pills)/PillBase";
import type { News2Result } from "@/lib/api";

const ROWS: [string, string][] = [
  ["resp_rate", "Resp rate"],
  ["spo2", "SpO₂"],
  ["on_oxygen", "Air / O₂"],
  ["systolic_bp", "Systolic BP"],
  ["heart_rate", "Pulse"],
  ["consciousness", "ACVPU"],
  ["temperature_c", "Temp °C"],
];

const BAND_TONE: Record<string, string> = {
  low: "text-fg",
  low_medium: "text-warn",
  medium: "text-warn",
  high: "text-alert",
};

export default function ({
  news2,
  showPrompt = false,
  className,
}: { news2?: News2Result | null; showPrompt?: boolean; className?: string }) {
  if (!news2 || news2.total === null || news2.total === undefined) {
    return (
      <Card title="NEWS2" className={className}>
        <p className="text-muted">No vitals yet. Run a camera scan or enter vitals manually.</p>
      </Card>
    );
  }
  const values = (news2.values_used ?? {}) as Record<string, unknown>;
  return (
    <Card
      title="NEWS2"
      className={className}
      aside={!news2.complete && <PillBase className="border-warn bg-warn-soft text-warn-fg">Partial</PillBase>}
    >
      <div className="flex items-baseline gap-[.75rem]">
        <span className={twMerge("text-[3rem] font-bold leading-none tabular-nums", BAND_TONE[news2.band ?? "low"])}>
          {news2.total}
        </span>
        <span className="text-[0.9375rem] font-medium capitalize">{(news2.band ?? "").replace("_", "–")} risk</span>
      </div>
      {!news2.complete && showPrompt && (
        <p className="mt-[.5rem] text-[0.875rem] text-warn-fg">
          Partial score — add {news2.missing.map((m) => ROWS.find((r) => r[0] === m)?.[1] ?? m).join(", ")} when a
          clinician is present.
        </p>
      )}
      <table className="mt-[.75rem] w-full text-[0.875rem] tabular-nums">
        <tbody>
          {ROWS.map(([key, label]) => {
            const score = news2.components[key];
            const value = values[key];
            return (
              <tr key={key} className="border-t-[1px] border-border">
                <td className="py-[.25rem] text-muted">{label}</td>
                <td className="py-[.25rem] text-right">
                  {value === undefined ? "—" : typeof value === "boolean" ? (value ? "Oxygen" : "Air") : String(value)}
                </td>
                <td
                  className={twMerge(
                    "w-[2.5rem] py-[.25rem] text-right font-semibold",
                    score === 3 && "text-alert",
                    score === 2 && "text-warn",
                  )}
                >
                  {score ?? "–"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Card>
  );
}
