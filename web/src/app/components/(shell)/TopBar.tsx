// Top bar: the mark on a sage disc, the three moments (pre-arrival, crew, hospital) in a floating pill, the active
// region and the presenter entry. Transparent: it sits on the canvas, not over it.
"use client";

import { Building2, House, Ship, Smartphone, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { twMerge } from "tailwind-merge";

import { APP_NAME } from "@/app/config";
import { setPresenterOpen } from "@/lib/presenter";
import { useMeta } from "@/lib/swr";

import styles from "./TopBar.module.scss";

const ROLES = [
  { href: "/pre-arrival", label: "Pre-arrival", icon: Smartphone },
  { href: "/crew", label: "Crew", icon: Ship },
  { href: "/hospital", label: "Hospital", icon: Building2 },
];

export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden>
      <path d="M3 12h4.2l2.1-4.6 3.6 9.2 2.4-4.6H21" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export default function () {
  const pathname = usePathname();
  const { data: meta } = useMeta();
  const companion = pathname.startsWith("/pre-arrival");
  // inside a packet, the wizard bar is the only chrome (it carries the mark), so the camera gets the room
  if (/^\/pre-arrival\/[^/]+/.test(pathname)) return null;
  return (
    // on a phone, the companion sees only their own screen: no crew or hospital tabs, no presenter tools
    <header className={twMerge(styles.bar, companion && styles.companion)}>
      <div className={styles.inner}>
        <Link href="/" className={styles.brand} aria-label={`${APP_NAME} home`} title="Home">
          <span className={styles.disc}>
            <Mark className="h-[1.125rem] w-[1.125rem]" />
          </span>
          <span className={styles.brandText}>{APP_NAME}</span>
        </Link>
        <nav className={twMerge("glass", styles.roles)} aria-label="Role">
          <Link href="/" className={twMerge(styles.role, styles.home, pathname === "/" && styles.active)} aria-label="Home" title="Home" aria-current={pathname === "/" ? "page" : undefined}>
            <House size={17} strokeWidth={1.75} />
          </Link>
          {ROLES.map(({ href, label, icon: Icon }) => {
            const active = pathname.startsWith(href);
            return (
              <Link key={href} href={href} className={twMerge(styles.role, active && styles.active)} aria-current={active ? "page" : undefined}>
                <Icon size={17} strokeWidth={1.75} />
                <span className={styles.roleLabel}>{label}</span>
              </Link>
            );
          })}
        </nav>
        <div className={styles.end}>
          {companion && (
            <Link href="/" className={styles.homeEnd} aria-label="Home" title="Home">
              <House size={17} strokeWidth={1.75} />
            </Link>
          )}
          {meta && <span className={styles.region}>{meta.region.name}</span>}
          <button
            type="button"
            className={styles.presenter}
            onClick={() => setPresenterOpen(true)}
            title="Presenter tools (Ctrl + .)"
            aria-label="Presenter tools"
          >
            <SlidersHorizontal size={17} strokeWidth={1.75} />
          </button>
        </div>
      </div>
    </header>
  );
}
