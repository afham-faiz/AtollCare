import { twMerge } from "tailwind-merge";

export default function ({ className, ...props }: React.JSX.IntrinsicElements["span"]) {
  return (
    <span
      className={twMerge(
        "inline-flex items-center gap-[.25rem] whitespace-nowrap rounded-[1rem] border-[1px] border-border bg-surface px-[.5rem] py-[.125rem] text-[0.875rem] font-medium leading-[1.25rem] text-fg",
        className,
      )}
      {...props}
    />
  );
}
