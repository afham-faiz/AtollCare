import { twMerge } from "tailwind-merge";

export default function ({ className, ...props }: React.JSX.IntrinsicElements["span"]) {
  return (
    <span
      className={twMerge(
        "inline-flex items-center gap-[.375rem] whitespace-nowrap rounded-full bg-well px-[.625rem] py-[.1875rem] text-[0.8125rem] font-[550] leading-[1.25rem] text-ink-2",
        className,
      )}
      {...props}
    />
  );
}
