import { twMerge } from "tailwind-merge";

import ButtonBase from "./ButtonBase";

export default function ({ className, ...props }: React.JSX.IntrinsicElements["button"]) {
  return (
    <ButtonBase
      className={twMerge("border-brand bg-brand text-white hover:border-brand-strong hover:bg-brand-strong", className)}
      {...props}
    />
  );
}
