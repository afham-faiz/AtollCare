// Quiet top bar: product mark, the three moments (pre-arrival, crew, hospital), active region, presenter entry.
"use client";

import { SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { twMerge } from "tailwind-merge";

import { APP_NAME } from "@/app/config";
import { setPresenterOpen } from "@/lib/presenter";
import { useMeta } from "@/lib/swr";

import styles from "./TopBar.module.scss";

const ROLES = [
  { href: "/pre-arrival", label: "Pre-arrival" },
  { href: "/crew", label: "Crew" },
  { href: "/hospital", label: "Hospital" },
];

export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="2.25" opacity="0.28" />
      <path d="M3 12h4.2l2.1-4.6 3.6 9.2 2.4-4.6H21" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function () {
  const pathname = usePathname();
  const { data: meta } = useMeta();
  return (
    // on a phone, the companion sees only their own screen: no crew or hospital tabs, no presenter tools
    <header className={twMerge(styles.bar, pathname.startsWith("/pre-arrival") && styles.companion)}>
      <div className={styles.inner}>
        <Link href="/crew" className={styles.brand}>
          <Mark className="h-[1.375rem] w-[1.375rem] text-teal" />
          <span className={styles.brandText}>{APP_NAME}</span>
        </Link>
        <nav className={styles.roles} aria-label="Role">
          {ROLES.map((r) => (
            <Link key={r.href} href={r.href} className={twMerge(styles.role, pathname.startsWith(r.href) && styles.active)}>
              {r.label}
            </Link>
          ))}
        </nav>
        <div className={styles.end}>
          {meta && <span className={styles.region}>{meta.region.name}</span>}
          <button
            type="button"
            className={styles.presenter}
            onClick={() => setPresenterOpen(true)}
            title="Presenter tools (Ctrl + .)"
            aria-label="Presenter tools"
          >
            <SlidersHorizontal size={16} />
          </button>
        </div>
      </div>
    </header>
  );
}
