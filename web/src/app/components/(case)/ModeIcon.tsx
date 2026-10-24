import { Ambulance, Car, Navigation, Plane, PlaneLanding, Ship, type LucideProps } from "lucide-react";

import type { TransportMode } from "@/lib/api";

const ICONS = {
  ground: Car,
  speedboat: Ship,
  sea_ambulance: Ambulance,
  seaplane: PlaneLanding,
  fixed_wing: Plane,
  helicopter: Navigation,
} as const;

export default function ({ mode, ...props }: LucideProps & { mode: TransportMode }) {
  const Icon = ICONS[mode];
  return <Icon size={16} aria-label={mode} {...props} />;
}
