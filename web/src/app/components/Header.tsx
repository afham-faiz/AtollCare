// F-M10.2 Header: fixed, scroll-aware, nav, role switcher, theme toggle (F-M10.4), mobile hamburger.
"use client";

import { Menu, Moon, Sun, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, useSyncExternalStore } from "react";
import { twMerge } from "tailwind-merge";

import { APP_NAME } from "@/app/config";
import { ROLES, setRole, useRole, type Role } from "@/lib/role";

import styles from "./Header.module.scss";

const NAV = [
  { href: "/report", label: "Report" },
  { href: "/hospital", label: "Hospital" },
  { href: "/transport", label: "Transport" },
  { href: "/demo", label: "Demo" },
];

const themeListeners = new Set<() => void>();
const readTheme = () => document.documentElement.dataset.theme ?? "system";

function useTheme(): [string, () => void] {
  const theme = useSyncExternalStore(
    (cb) => {
      themeListeners.add(cb);
      return () => themeListeners.delete(cb);
    },
    readTheme,
    () => "system",
  );
  const toggle = () => {
    const current =
      document.documentElement.dataset.theme ??
      (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    const next = current === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try {
      localStorage.setItem("atollcare.theme", next);
    } catch {
      // storage unavailable
    }
    themeListeners.forEach((l) => l());
  };
  return [theme, toggle];
}

export default function () {
  const pathname = usePathname();
  const role = useRole();
  const [theme, toggleTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  const nav = NAV.map((n) => (
    <Link
      key={n.href}
      href={n.href}
      className={twMerge(styles.link, pathname.startsWith(n.href) && styles.active)}
    >
      {n.label}
    </Link>
  ));

  return (
    <header className={twMerge(styles.header, scrolled && styles.scrolled)}>
      <div className={styles.bar}>
        <Link href="/" className={styles.logo}>
          <span className={styles.mark} aria-hidden />
          {APP_NAME}
        </Link>
        <nav className={styles.desktopNav}>{nav}</nav>
        <div className={styles.controls}>
          <label className={styles.role}>
            <span className="sr-only">Role</span>
            <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Current role">
              {ROLES.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.label}
                </option>
              ))}
            </select>
          </label>
          <button type="button" className={styles.icon} onClick={toggleTheme} aria-label="Toggle dark mode">
            {theme === "dark" ? <Sun size={20} /> : <Moon size={20} />}
          </button>
          <button
            type="button"
            className={twMerge(styles.icon, styles.burger)}
            onClick={() => setOpen((o) => !o)}
            aria-label="Menu"
            aria-expanded={open}
          >
            {open ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>
      <nav className={twMerge(styles.mobileNav, open && styles.open)}>{nav}</nav>
    </header>
  );
}
