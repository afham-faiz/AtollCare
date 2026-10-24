// F-M10.3 Case timeline: relative + absolute sim times, actor icons, durations between key events.
import { Bot, Building2, Hospital, Phone, Stethoscope, Truck, User } from "lucide-react";

import Card from "@/app/components/Card";
import type { CaseEvent } from "@/lib/api";
import { fmtMin, fmtRelative, fmtTime, minutesBetween } from "@/lib/format";

const ACTOR_ICON: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  reporter: Phone,
  clinician: Stethoscope,
  specialist: Hospital,
  transport: Truck,
  system: Bot,
  demo: Building2,
};

const KEY = new Set(["submitted", "referred", "accepted", "dispatched", "departed", "arrived", "closed"]);

export default function ({ events, now, className }: { events: CaseEvent[]; now?: string | null; className?: string }) {
  let lastKey: string | null = null;
  return (
    <Card title="Timeline" className={className}>
      {events.length === 0 && <p className="text-muted">No events yet.</p>}
      <ol className="relative flex flex-col gap-[.75rem] border-l-[1px] border-border pl-[1rem]">
        {events.map((e) => {
          const Icon = ACTOR_ICON[e.actor_role] ?? User;
          let gap: number | null = null;
          if (KEY.has(e.type)) {
            gap = lastKey ? minutesBetween(lastKey, e.at) : null;
            lastKey = e.at;
          }
          return (
            <li key={e.id} className="relative">
              <span className="absolute left-[-1.5rem] top-[.125rem] flex h-[1rem] w-[1rem] items-center justify-center rounded-[50%] bg-raised">
                <Icon size={16} className={KEY.has(e.type) ? "text-brand" : "text-muted"} />
              </span>
              <p className="text-[0.875rem]">{e.summary}</p>
              <p className="text-[0.875rem] text-muted tabular-nums">
                {fmtTime(e.at)} · {fmtRelative(e.at, now)} · {e.actor_role}
                {gap !== null && gap > 0 && <span className="text-brand"> · +{fmtMin(gap)} since previous step</span>}
              </p>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}
