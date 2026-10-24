"use client";

import dynamic from "next/dynamic";

import Skeleton from "@/app/components/Skeleton";

// Leaflet touches `window` at import time → client-only.
export default dynamic(() => import("./TransferMap"), {
  ssr: false,
  loading: () => <Skeleton className="h-[16rem] w-full" />,
});
