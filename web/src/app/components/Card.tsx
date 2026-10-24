import { twMerge } from "tailwind-merge";

export default function ({
  title,
  aside,
  className,
  children,
  ...props
}: Omit<React.JSX.IntrinsicElements["section"], "title"> & { title?: React.ReactNode; aside?: React.ReactNode }) {
  return (
    <section
      className={twMerge("rounded-[.75rem] border-[1px] border-border bg-raised p-[1rem] min-w-0", className)}
      {...props}
    >
      {(title || aside) && (
        <header className="mb-[.75rem] flex flex-wrap items-center justify-between gap-[.5rem]">
          <h2 className="text-[0.875rem] font-semibold uppercase tracking-[0.04em] text-muted">{title}</h2>
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}
