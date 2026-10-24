import { twMerge } from "tailwind-merge";

export default function ({ className, ...props }: React.JSX.IntrinsicElements["div"]) {
  return <div className={twMerge("animate-skeleton rounded-[.5rem] bg-surface h-[1rem]", className)} {...props} />;
}
