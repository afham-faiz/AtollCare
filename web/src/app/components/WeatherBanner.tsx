// F-M4.7 Weather & daylight banner: sim time, sunrise/sunset, sea state, wind, visibility, disabled modes + why.
"use client";

import { Moon, Sun, Waves, Wind, Eye } from "lucide-react";

import SourceBadge from "@/app/components/SourceBadge";
import type { MetaResponse } from "@/lib/api";
import { MODE_LABEL } from "@/lib/format";

export default function ({ meta }: { meta: MetaResponse }) {
  const { clock, demo_state: st } = meta;
  const disabled = Object.entries(clock.disabled_modes);
  return (
    <section className="flex flex-col gap-[.5rem] rounded-[.75rem] border-[1px] border-border bg-surface p-[1rem]">
      <div className="flex flex-wrap items-center gap-x-[1.25rem] gap-y-[.5rem] text-[0.9375rem] tabular-nums">
        <span className="flex items-center gap-[.375rem] text-[1.25rem] font-bold">
          {clock.is_daylight ? <Sun size={20} className="text-warn" /> : <Moon size={20} className="text-brand" />}
          {clock.local_time}
          <span className="text-[0.875rem] font-normal text-muted">sim · ×{st.speed_multiplier}</span>
        </span>
        <span>Sunrise {clock.sunrise} · Sunset {clock.sunset} · Seaplane last landing {clock.seaplane_last_landing}</span>
        <span className="flex items-center gap-[.25rem]"><Waves size={16} /> Sea state {st.weather.sea_state}</span>
        <span className="flex items-center gap-[.25rem]"><Wind size={16} /> {st.weather.wind_kt} kt</span>
        <span className="flex items-center gap-[.25rem]"><Eye size={16} /> {st.weather.visibility_km} km</span>
        <SourceBadge kind="assumption" />
      </div>
      {disabled.length > 0 ? (
        <ul className="flex flex-col gap-[.125rem] text-[0.875rem]">
          {disabled.map(([mode, why]) => (
            <li key={mode}>
              <strong className="text-alert">{MODE_LABEL[mode as keyof typeof MODE_LABEL] ?? mode} disabled:</strong> {why}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-[0.875rem] text-brand">All transport modes available.</p>
      )}
    </section>
  );
}
