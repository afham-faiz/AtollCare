// F-M1.1 One-tap alert: giant button, searchable origin island (default from localStorage), optional patient.
"use client";

import { Loader2, Siren } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { DEFAULT_ORIGIN_ID } from "@/app/config";
import { post, type Case } from "@/lib/api";
import { useMeta } from "@/lib/swr";
import { toastError } from "@/lib/toast";

import styles from "./Report.module.scss";

const ORIGIN_KEY = "atollcare.origin";

export default function () {
  const router = useRouter();
  const { data: meta } = useMeta();
  const [origin, setOrigin] = useState(DEFAULT_ORIGIN_ID);
  const [query, setQuery] = useState("");
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [sex, setSex] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(ORIGIN_KEY);
      if (saved) setOrigin(saved);
    } catch {
      // ignore
    }
  }, []);

  const origins = useMemo(
    () => (meta?.facilities ?? []).filter((f) => f.type !== "airport"),
    [meta],
  );
  const filtered = origins.filter((f) => `${f.name} ${f.atoll}`.toLowerCase().includes(query.toLowerCase()));

  const raise = async () => {
    setBusy(true);
    try {
      localStorage.setItem(ORIGIN_KEY, origin);
    } catch {
      // ignore
    }
    try {
      const c = await post<Case>("/cases", {
        origin_facility_id: origin,
        patient: {
          name: name || null,
          age: age ? Number(age) : null,
          sex: sex || null,
        },
      });
      router.push(`/report/${c.id}`);
    } catch (err) {
      toastError(err);
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto flex max-w-[36rem] flex-col gap-[1rem]">
      <button type="button" className={styles.alert} onClick={raise} disabled={busy}>
        {busy ? <Loader2 size={48} className="animate-spin" /> : <Siren size={48} />}
        <span>Raise medical alert</span>
        <small>Creates a case and alerts the health centre</small>
      </button>

      <label className={styles.field}>
        <span>Island / health centre</span>
        <input
          type="search"
          placeholder="Search islands…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          aria-label="Search islands"
        />
        <select value={origin} onChange={(e) => setOrigin(e.target.value)} size={Math.min(6, Math.max(2, filtered.length))}>
          {filtered.map((f) => (
            <option key={f.id} value={f.id}>
              {f.name}
            </option>
          ))}
        </select>
      </label>

      <details className="rounded-[.75rem] border-[1px] border-border p-[1rem]">
        <summary className="min-h-[2rem] cursor-pointer font-medium">Patient (optional)</summary>
        <div className="mt-[.75rem] grid grid-cols-2 gap-[.75rem]">
          <label className={`${styles.field} col-span-2`}>
            <span>Name</span>
            <input value={name} onChange={(e) => setName(e.target.value)} autoComplete="off" />
          </label>
          <label className={styles.field}>
            <span>Age</span>
            <input type="number" inputMode="numeric" value={age} onChange={(e) => setAge(e.target.value)} />
          </label>
          <label className={styles.field}>
            <span>Sex</span>
            <select value={sex} onChange={(e) => setSex(e.target.value)}>
              <option value="">—</option>
              <option value="F">Female</option>
              <option value="M">Male</option>
              <option value="X">Other</option>
            </select>
          </label>
        </div>
      </details>
      <p className="text-[0.875rem] text-muted">
        In an emergency also call your island health centre. This tool supports, and never replaces, clinical decisions.
      </p>
    </div>
  );
}
