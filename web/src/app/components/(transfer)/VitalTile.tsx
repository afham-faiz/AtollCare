// One vital sign: the number is the biggest thing on the tile; source and age are quiet.
import { twMerge } from "tailwind-merge";

import styles from "./VitalTile.module.scss";

export type Tone = "normal" | "warn" | "alert" | "muted";

export default function ({
  label,
  value,
  unit,
  icon,
  note,
  tone = "normal",
  size = "md",
  className,
  children,
}: {
  label: string;
  value: React.ReactNode;
  unit?: string;
  icon?: React.ReactNode;
  note?: React.ReactNode;
  tone?: Tone;
  size?: "md" | "lg";
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <div className={twMerge(styles.tile, styles[tone], className)}>
      <div className={styles.label}>
        {icon}
        {label}
      </div>
      <div className={twMerge(styles.value, size === "lg" && styles.large)}>
        {value}
        {unit && <span className={styles.unit}>{unit}</span>}
      </div>
      {note && <div className={styles.note}>{note}</div>}
      {children}
    </div>
  );
}
