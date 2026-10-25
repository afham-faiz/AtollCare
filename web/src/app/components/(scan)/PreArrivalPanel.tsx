// What arrived before the crew did, and every scan since: the companion's account in their own words, the ID as it
// was read (marked when it needs checking by eye), and each video's results with the frames behind every finding.
// Read-only; the crew and the receiving hospital see the same thing.
"use client";

import { ShieldAlert, ShieldCheck } from "lucide-react";

import type { Transfer } from "@/lib/api";
import { fmtTime } from "@/lib/format";

import styles from "./PreArrivalPanel.module.scss";
import ScanResult from "./ScanResult";

export default function ({ t, tz }: { t: Transfer; tz?: string }) {
  const p = t.pre_arrival;
  const id = p?.identity;
  const crewScans = [...t.scans].reverse();
  const rows = id
    ? ([
        ["Name", id.full_name],
        ["Age", id.age != null ? String(id.age) : null],
        ["Date of birth", id.date_of_birth],
        ["ID number", id.id_number],
        ["Document", id.document_type],
      ] as const)
    : [];

  return (
    <div className={styles.panel}>
      {p && (
        <section className={styles.section}>
          <header className={styles.head}>
            <h3 className={styles.title}>Sent ahead by the companion</h3>
            <span className={styles.meta}>
              <span className="font-mono">{p.code}</span>
              {p.sent_at ? ` · sent ${fmtTime(p.sent_at, tz)}` : ""}
            </span>
          </header>

          {p.account ? (
            <blockquote className={styles.account}>
              “{p.account}”
              <span className={styles.accountMeta}>{p.account_source === "voice" ? "Spoken, transcribed word for word" : "Typed by the companion"}</span>
            </blockquote>
          ) : (
            <p className={styles.note}>No account was given.</p>
          )}

          {id && (
            <div className={styles.id}>
              <p className={id.needs_review ? styles.review : styles.clear}>
                {id.needs_review ? <ShieldAlert size={16} /> : <ShieldCheck size={16} />}
                {id.needs_review ? "ID photo · check by eye" : "ID photo · read clearly"}
              </p>
              <dl>
                {rows.map(([k, v]) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd className={v ? "" : "text-ink-3"}>{v ?? "Not read"}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {p.scans.map((s) => (
            <div key={s.id} className={styles.scan}>
              <ScanResult scan={s} tz={tz} title="Companion’s video" bystander />
            </div>
          ))}
        </section>
      )}

      {crewScans.length > 0 && (
        <section className={styles.section}>
          <header className={styles.head}>
            <h3 className={styles.title}>Crew scans</h3>
            <span className={styles.meta}>{crewScans.length === 1 ? "1 scan" : `${crewScans.length} scans`} · newest first</span>
          </header>
          {crewScans.map((s, i) => (
            <div key={s.id} className={styles.scan}>
              <ScanResult scan={s} tz={tz} title={`Scan ${crewScans.length - i}`} />
            </div>
          ))}
        </section>
      )}

      {!p && !crewScans.length && <p className={styles.note}>No video, account or ID came with this transfer.</p>}
    </div>
  );
}
