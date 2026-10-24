import { twMerge } from "tailwind-merge";

import styles from "./Button.module.scss";

export type ButtonSize = "sm" | "md" | "lg";

export default function ({
  className,
  type = "button",
  size = "md",
  ...props
}: React.JSX.IntrinsicElements["button"] & { size?: ButtonSize }) {
  return <button type={type} className={twMerge(styles.button, styles[size], styles.quiet, className)} {...props} />;
}
