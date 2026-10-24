import { twMerge } from "tailwind-merge";

import styles from "./Button.module.scss";
import type { ButtonSize } from "./ButtonBase";

export default function ({
  className,
  type = "button",
  size = "md",
  ...props
}: React.JSX.IntrinsicElements["button"] & { size?: ButtonSize }) {
  return <button type={type} className={twMerge(styles.button, styles[size], styles.primary, className)} {...props} />;
}
