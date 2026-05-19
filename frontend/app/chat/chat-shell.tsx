"use client";

import { Sidebar } from "@/components/chat/sidebar";
import type { Conversation } from "@/lib/api";

export function ChatShell({
  initialConversations,
  initialJournaled,
  children,
}: {
  initialConversations: Conversation[];
  initialJournaled: boolean;
  children: React.ReactNode;
}) {
  return (
    // h-dvh = dynamic viewport. overflow-hidden prevents flex children from
    // growing past viewport (which would make the outer page scroll instead
    // of the inner panels — that's the "sidebar scrolls away" bug).
    <div className="flex h-dvh overflow-hidden">
      <Sidebar
        initialConversations={initialConversations}
        initialJournaled={initialJournaled}
      />
      <div className="flex-1 flex flex-col min-w-0 min-h-0 pt-[calc(env(safe-area-inset-top)+56px)] md:pt-0">
        {children}
      </div>
    </div>
  );
}
