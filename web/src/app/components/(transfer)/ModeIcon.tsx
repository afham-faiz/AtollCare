import { Ambulance, Plane, Ship, type LucideProps } from "lucide-react";

import type { TransportMode } from "@/lib/api";

function Helicopter(props: LucideProps) {
  // lucide has no helicopter glyph; a plane rotated upward reads as "air" without inventing an icon set
  return <Plane {...props} style={{ transform: "rotate(-45deg)" }} />;
}

const ICONS = { road: Ambulance, boat: Ship, helicopter: Helicopter, plane: Plane } as const;

export default function ({ mode, ...props }: LucideProps & { mode: TransportMode }) {
  const Icon = ICONS[mode];
  return <Icon size={16} strokeWidth={1.75} aria-hidden {...props} />;
}
