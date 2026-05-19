"use client";

import { BackToLastChat } from "@/components/navigation/back-to-last-chat";

export function BackToChatButton() {
  return (
    <BackToLastChat className="inline-flex h-10 items-center justify-center rounded-full border border-border bg-fg/[0.035] px-4 text-sm font-medium text-fg-muted shadow-sm transition hover:bg-fg/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 active:scale-[0.98]">
      Back to chat
    </BackToLastChat>
  );
}
