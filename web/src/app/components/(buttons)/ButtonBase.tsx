import { twMerge } from "tailwind-merge";

export default function ({ className, type = "button", ...props }: React.JSX.IntrinsicElements["button"]) {
  return (
    <button
      type={type}
      className={twMerge(
        "inline-flex min-h-[2.75rem] items-center justify-center gap-[.5rem] rounded-[.5rem] border-[1px] border-border bg-surface px-[1rem] text-[0.9375rem] font-medium text-fg transition-colors hover:bg-subtle disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
