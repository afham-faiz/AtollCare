// F-M1.2 Structured intake chips: complaint, red flags, suspected conditions with probability bars.
import Card from "@/app/components/Card";
import SourceBadge from "@/app/components/SourceBadge";
import PillBase from "@/app/components/(pills)/PillBase";
import type { Intake } from "@/lib/api";
import { CONDITION_LABEL, fmtTime } from "@/lib/format";

export default function ({ intake, className, children }: { intake?: Intake | null; className?: string; children?: React.ReactNode }) {
  if (!intake) {
    return (
      <Card title="Intake" className={className}>
        <p className="text-muted">No description analysed yet.</p>
      </Card>
    );
  }
  return (
    <Card
      title="Intake"
      className={className}
      aside={<SourceBadge kind={intake.extracted_by === "gemini" ? "gemini" : "fallback"} />}
    >
      <p className="text-[1.0625rem] font-semibold">{intake.chief_complaint}</p>
      <p className="text-[0.875rem] text-muted">
        Onset {intake.onset_time ? `${fmtTime(intake.onset_time)} (${intake.onset_confidence})` : "unknown"} · language{" "}
        {intake.language}
      </p>
      {intake.red_flags.length > 0 && (
        <div className="mt-[.5rem] flex flex-wrap gap-[.375rem]">
          {intake.red_flags.map((f) => (
            <PillBase key={f} className="border-alert bg-alert-soft text-alert">
              {f}
            </PillBase>
          ))}
        </div>
      )}
      {intake.symptoms.length > 0 && (
        <div className="mt-[.5rem] flex flex-wrap gap-[.375rem]">
          {intake.symptoms.map((s) => (
            <PillBase key={s}>{s}</PillBase>
          ))}
        </div>
      )}
      <ul className="mt-[.75rem] flex flex-col gap-[.375rem]">
        {intake.suspected_conditions.map((s) => (
          <li key={s.condition_id} title={s.rationale}>
            <div className="flex justify-between text-[0.875rem]">
              <span>{CONDITION_LABEL[s.condition_id] ?? s.condition_id}</span>
              <span className="tabular-nums">{Math.round(s.probability * 100)}%</span>
            </div>
            <div className="h-[.375rem] rounded-[.25rem] bg-surface">
              <div className="h-full rounded-[.25rem] bg-brand" style={{ width: `${s.probability * 100}%` }} />
            </div>
          </li>
        ))}
      </ul>
      {children}
    </Card>
  );
}
