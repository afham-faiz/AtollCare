// F-M8.2 World controls: sim clock, speed multiplier, sea state, wind, visibility, helicopter, night override.
"use client";

import { useState } from "react";
import { mutate } from "swr";
import { twMerge } from "tailwind-merge";

import ButtonBase from "@/app/components/(buttons)/ButtonBase";
import Card from "@/app/components/Card";
import { patch, type DemoStatePatch, type MetaResponse } from "@/lib/api";
import { toastError } from "@/lib/toast";

const SPEEDS = [1, 10, 60, 300];

export default function ({ meta }: { meta: MetaResponse }) {
  const st = meta.demo_state;
  const [time, setTime] = useState("");
  const apply = async (body: Partial<DemoStatePatch>) => {
    try {
      await patch("/demo/state", body);
      await Promise.all([mutate("/meta"), mutate("/demo/state")]);
    } catch (err) {
      toastError(err);
    }
  };
  const night = st.night_override === null || st.night_override === undefined ? "auto" : st.night_override ? "night" : "day";

  return (
    <Card title="World controls">
      <div className="flex flex-col gap-[1rem]">
        <div>
          <p className="mb-[.375rem] text-[0.875rem] text-muted">
            Sim clock: <strong className="text-fg tabular-nums">{meta.clock.local_time}</strong> ({meta.clock.is_daylight ? "day" : "night"})
          </p>
          <div className="flex flex-wrap gap-[.5rem]">
            <ButtonBase onClick={() => apply({ set_time_of_day: "14:00" })}>Day 14:00</ButtonBase>
            <ButtonBase onClick={() => apply({ set_time_of_day: "21:00" })}>Night 21:00</ButtonBase>
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
              className="h-[2.75rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.5rem]"
              aria-label="Set time of day"
            />
            <ButtonBase disabled={!time} onClick={() => apply({ set_time_of_day: time })}>
              Set
            </ButtonBase>
          </div>
        </div>
        <div>
          <p className="mb-[.375rem] text-[0.875rem] text-muted">Speed multiplier</p>
          <div className="flex flex-wrap gap-[.5rem]">
            {SPEEDS.map((s) => (
              <ButtonBase
                key={s}
                onClick={() => apply({ speed_multiplier: s })}
                className={twMerge(st.speed_multiplier === s && "border-brand bg-brand-soft text-brand")}
              >
                {s}×
              </ButtonBase>
            ))}
          </div>
        </div>
        <label className="flex flex-col gap-[.25rem] text-[0.875rem]">
          <span>
            Sea state <strong className="tabular-nums">{st.weather.sea_state}</strong>{" "}
            <span className="text-muted">(speedboat off ≥ 5, sea ambulance off ≥ 6)</span>
          </span>
          <input
            type="range"
            min={0}
            max={9}
            value={st.weather.sea_state}
            onChange={(e) => apply({ weather: { sea_state: Number(e.target.value) } })}
            className="accent-[var(--brand)]"
          />
        </label>
        <label className="flex flex-col gap-[.25rem] text-[0.875rem]">
          <span>
            Wind <strong className="tabular-nums">{st.weather.wind_kt} kt</strong> <span className="text-muted">(seaplane off ≥ 25)</span>
          </span>
          <input
            type="range"
            min={0}
            max={50}
            value={st.weather.wind_kt}
            onChange={(e) => apply({ weather: { wind_kt: Number(e.target.value) } })}
            className="accent-[var(--brand)]"
          />
        </label>
        <label className="flex flex-col gap-[.25rem] text-[0.875rem]">
          <span>
            Visibility <strong className="tabular-nums">{st.weather.visibility_km} km</strong>{" "}
            <span className="text-muted">(seaplane off &lt; 5, fixed-wing off &lt; 2)</span>
          </span>
          <input
            type="range"
            min={0}
            max={20}
            value={st.weather.visibility_km}
            onChange={(e) => apply({ weather: { visibility_km: Number(e.target.value) } })}
            className="accent-[var(--brand)]"
          />
        </label>
        <label className="flex min-h-[2.75rem] items-center justify-between gap-[.5rem] text-[0.875rem]">
          Helicopter enabled (hypothetical asset)
          <input
            type="checkbox"
            checked={st.helicopter_enabled}
            onChange={(e) => apply({ helicopter_enabled: e.target.checked })}
            className="h-[1.25rem] w-[1.25rem]"
          />
        </label>
        <label className="flex min-h-[2.75rem] items-center justify-between gap-[.5rem] text-[0.875rem]">
          Daylight
          <select
            value={night}
            onChange={(e) =>
              apply(
                e.target.value === "auto"
                  ? { clear_night_override: true }
                  : { night_override: e.target.value === "night" },
              )
            }
            className="h-[2.5rem] rounded-[.5rem] border-[1px] border-border bg-raised px-[.5rem]"
          >
            <option value="auto">From clock</option>
            <option value="day">Force day</option>
            <option value="night">Force night</option>
          </select>
        </label>
      </div>
    </Card>
  );
}
