"use client";

import { X } from "lucide-react";

import ModalBase from "./ModalBase";

export default function ({
  title,
  subtitle,
  footer,
  children,
  ...props
}: React.ComponentProps<typeof ModalBase> & { title: string; subtitle?: string; footer?: React.ReactNode }) {
  return (
    <ModalBase {...props}>
      <div className="mb-[1.25rem] flex items-start justify-between gap-[1rem]">
        <div>
          <h2 className="text-[1.1875rem] font-[650] tracking-[-0.015em]">{title}</h2>
          {subtitle && <p className="mt-[.125rem] text-[0.875rem] text-ink-2">{subtitle}</p>}
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={props.onClose}
          className="flex h-[2.25rem] w-[2.25rem] items-center justify-center rounded-[.625rem] text-ink-3 hover:bg-well hover:text-ink"
        >
          <X size={18} />
        </button>
      </div>
      <div className="flex flex-col gap-[1rem]">{children}</div>
      {footer && <div className="mt-[1.5rem] flex flex-wrap justify-end gap-[.5rem]">{footer}</div>}
    </ModalBase>
  );
}
