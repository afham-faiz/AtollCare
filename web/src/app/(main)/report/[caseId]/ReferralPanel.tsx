// F-M1.6 Clinician referral: destination override (capable facilities only), SBAR preview, editable note.
"use client";

import { Send } from "lucide-react";
import { useState } from "react";
import useSWR from "swr";

import ButtonPrimary from "@/app/components/(buttons)/ButtonPrimary";
import SbarSummaryCard from "@/app/components/(case)/SbarSummary";
import Card from "@/app/components/Card";
import { fetcher, post, type Case, type Facility, type SbarSummary } from "@/lib/api";
import { useCaseAction } from "@/lib/actions";
import { facilityName } from "@/lib/format";

import styles from "../Report.module.scss";

export default function ({ c, facilities }: { c: Case; facilities: Facility[] }) {
  const rec = c.recommendation;
  const [dest, setDest] = useState("");
  const [note, setNote] = useState("");
  const { busy, run } = useCaseAction(c.id);
  const { data: sbar } = useSWR<SbarSummary>(rec ? [`/cases/${c.id}/sbar`, rec.input_hash, c.patient] : null, ([p]: [string]) =>
    fetcher<SbarSummary>(p),
  );
  if (!rec) return null;
  const capable = facilities.filter(
    (f) => f.type !== "airport" && f.type !== "health_centre" && rec.required_capabilities.every((cap) => f.capabilities.includes(cap)),
  );
  const target = dest || rec.destination_id;
  const sent = c.referral && ["referred", "needs_info", "accepted"].includes(c.status);

  return (
    <Card title="3 · Referral (clinician)">
      {sent ? (
        <p className="text-[0.9375rem]">
          Referral sent to <strong>{facilityName(facilities, c.referral?.destination_id)}</strong> — status{" "}
          <strong>{c.referral?.response}</strong>.
        </p>
      ) : (
        <div className="flex flex-col gap-[.75rem]">
          <label className={styles.field}>
            <span>Destination (recommended: {facilityName(facilities, rec.destination_id)})</span>
            <select value={target} onChange={(e) => setDest(e.target.value)}>
              {capable.map((f) => (
                <option key={f.id} value={f.id}>
                  {f.name}
                  {f.id === rec.destination_id ? " — recommended" : ""}
                </option>
              ))}
            </select>
          </label>
          <SbarSummaryCard sbar={sbar} title="SBAR preview" className="bg-surface" />
          <label className={styles.field}>
            <span>Note to specialist (optional)</span>
            <textarea value={note} onChange={(e) => setNote(e.target.value)} className="min-h-[4rem]" />
          </label>
          <ButtonPrimary
            disabled={busy}
            onClick={() =>
              run(() =>
                post<Case>(`/cases/${c.id}/refer`, {
                  destination_id: target,
                  note: note || null,
                  route_id: target === rec.destination_id ? rec.chosen_route_id : null,
                }),
              )
            }
          >
            <Send size={20} /> Send referral to {facilityName(facilities, target)}
          </ButtonPrimary>
        </div>
      )}
    </Card>
  );
}
