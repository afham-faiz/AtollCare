import { twMerge } from "tailwind-merge";

import ButtonBase from "./ButtonBase";

export default function ({ className, ...props }: React.JSX.IntrinsicElements["button"]) {
  return (
    <ButtonBase
      className={twMerge("border-brand bg-brand text-brand-fg hover:bg-brand hover:opacity-90", className)}
      {...props}
    />
  );
}
