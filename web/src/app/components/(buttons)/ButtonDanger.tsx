import { twMerge } from "tailwind-merge";

import ButtonBase from "./ButtonBase";

export default function ({ className, ...props }: React.JSX.IntrinsicElements["button"]) {
  return (
    <ButtonBase
      className={twMerge("border-alert bg-alert text-white hover:bg-alert hover:opacity-90", className)}
      {...props}
    />
  );
}
