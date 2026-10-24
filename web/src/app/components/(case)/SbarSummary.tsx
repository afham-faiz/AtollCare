// F-M2.7 SBAR referral summary card.
import Card from "@/app/components/Card";
import SourceBadge from "@/app/components/SourceBadge";
import type { SbarSummary } from "@/lib/api";

export default function ({ sbar, title = "SBAR referral", className }: { sbar?: SbarSummary | null; title?: string; className?: string }) {
  if (!sbar) {
    return (
      <Card title={title} className={className}>
        <p className="text-muted">SBAR is generated when the referral is sent.</p>
      </Card>
    );
  }
  const rows: [string, string][] = [
    ["S", sbar.situation],
    ["B", sbar.background],
    ["A", sbar.assessment],
    ["R", sbar.recommendation],
  ];
  return (
    <Card title={title} className={className} aside={<SourceBadge kind={sbar.generated_by === "gemini" ? "gemini" : "template"} />}>
      <dl className="flex flex-col gap-[.5rem]">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-[.75rem]">
            <dt className="w-[1.5rem] shrink-0 text-[1.125rem] font-bold text-brand">{k}</dt>
            <dd className="text-[0.9375rem]">{v}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}
