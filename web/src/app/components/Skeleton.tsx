import { twMerge } from "tailwind-merge";

export default function ({ className, ...props }: React.JSX.IntrinsicElements["div"]) {
  return <div className={twMerge("animate-skeleton h-[1rem] rounded-[.75rem] bg-well", className)} {...props} />;
}
