"use client";

import Sheet from "@/app/components/(modals)/Sheet";
import { setPresenterOpen, usePresenterOpen, usePresenterShortcut } from "@/lib/presenter";

import PresenterTools from "./PresenterTools";

export default function () {
  usePresenterShortcut();
  const open = usePresenterOpen();
  return (
    <Sheet open={open} onClose={() => setPresenterOpen(false)} title="Presenter" subtitle="Ctrl + . to open or close">
      <PresenterTools onDone={() => setPresenterOpen(false)} />
    </Sheet>
  );
}
