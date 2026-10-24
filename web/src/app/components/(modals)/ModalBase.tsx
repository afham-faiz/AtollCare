"use client";

import { useEffect } from "react";
import { twMerge } from "tailwind-merge";

import styles from "./Modal.module.scss";

export default function ({
  open,
  onClose,
  className,
  children,
  ...props
}: React.JSX.IntrinsicElements["div"] & { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div className={styles.backdrop} onClick={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        className={twMerge(styles.panel, className)}
        onClick={(e) => e.stopPropagation()}
        {...props}
      >
        {children}
      </div>
    </div>
  );
}
