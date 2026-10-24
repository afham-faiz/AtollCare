// Side sheet for progressive disclosure (review handoff, notes history, presenter tools).
"use client";

import { X } from "lucide-react";
import { useEffect } from "react";
import { twMerge } from "tailwind-merge";

import styles from "./Sheet.module.scss";

export default function ({
  open,
  onClose,
  title,
  subtitle,
  footer,
  className,
  panelRef,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: React.ReactNode;
  subtitle?: React.ReactNode;
  footer?: React.ReactNode;
  className?: string;
  panelRef?: React.Ref<HTMLDivElement>;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className={styles.root}>
      <div className={styles.backdrop} onClick={onClose} />
      <aside ref={panelRef} role="dialog" aria-modal="true" className={twMerge(styles.panel, className)}>
        <header className={styles.header}>
          <div className="min-w-0">
            <h2 className={styles.title}>{title}</h2>
            {subtitle && <p className={styles.subtitle}>{subtitle}</p>}
          </div>
          <button type="button" aria-label="Close" onClick={onClose} className={styles.close}>
            <X size={18} />
          </button>
        </header>
        <div className={styles.body}>{children}</div>
        {footer && <footer className={styles.footer}>{footer}</footer>}
      </aside>
    </div>
  );
}
