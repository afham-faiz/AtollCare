"use client";

import { X } from "lucide-react";

import ModalBase from "./ModalBase";

export default function ({
  title,
  footer,
  children,
  ...props
}: React.ComponentProps<typeof ModalBase> & { title: string; footer?: React.ReactNode }) {
  return (
    <ModalBase {...props}>
      <div className="mb-[1rem] flex items-start justify-between gap-[1rem]">
        <h2 className="text-[1.125rem] font-semibold">{title}</h2>
        <button type="button" aria-label="Close" onClick={props.onClose} className="text-muted hover:text-fg">
          <X size={20} />
        </button>
      </div>
      <div className="flex flex-col gap-[.75rem]">{children}</div>
      {footer && <div className="mt-[1.25rem] flex flex-wrap justify-end gap-[.5rem]">{footer}</div>}
    </ModalBase>
  );
}
