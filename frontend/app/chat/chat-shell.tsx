"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
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
  const qc = useQueryClient();
  const [hydrated, setHydrated] = useState(false);

  if (!hydrated) {
    qc.setQueryData(["conversations"], initialConversations);
    qc.setQueryData(["journal", "today"], {
      entry: initialJournaled ? { id: "hydrated" } : null,
    });
    setHydrated(true);
  }

  return (
    // h-dvh = dynamic viewport. overflow-hidden prevents flex children from
    // growing past viewport (which would make the outer page scroll instead
    // of the inner panels — that's the "sidebar scrolls away" bug).
    <div className="flex h-dvh overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 min-h-0 pt-[calc(env(safe-area-inset-top)+56px)] md:pt-0">
        {children}
      </div>
    </div>
  );
}
