// Minimal header: logo, the two screens, active region.
"use client";

import { MapPin } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { twMerge } from "tailwind-merge";

import { APP_NAME } from "@/app/config";
import { useMeta } from "@/lib/swr";

const NAV = [
  { href: "/crew", label: "Crew" },
  { href: "/hospital", label: "Hospital" },
];

export default function () {
  const pathname = usePathname();
  const { data: meta } = useMeta();
  return (
    <header className="sticky top-0 z-[1500] border-b-[1px] border-border bg-surface">
      <div className="mx-auto flex h-[3.5rem] max-w-[90rem] items-center gap-[1.5rem] px-[1rem]">
        <Link href="/" className="flex items-center gap-[.5rem] text-[1.0625rem] font-bold">
          <span className="h-[1.125rem] w-[1.125rem] rounded-[50%] border-[.3125rem] border-brand" aria-hidden />
          {APP_NAME}
        </Link>
        <nav className="flex gap-[.25rem]">
          {NAV.map((n) => (
            <Link
              key={n.href}
              href={n.href}
              className={twMerge(
                "rounded-[.5rem] px-[.75rem] py-[.5rem] font-medium text-muted hover:bg-subtle hover:text-fg",
                pathname.startsWith(n.href) && "bg-brand-soft text-brand-strong",
              )}
            >
              {n.label}
            </Link>
          ))}
        </nav>
        {meta && (
          <span className="ml-auto hidden items-center gap-[.375rem] text-[0.875rem] text-muted sm:flex">
            <MapPin size={16} /> {meta.region.name}
          </span>
        )}
      </div>
    </header>
  );
}
