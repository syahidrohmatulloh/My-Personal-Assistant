"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
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

  // Seed cache once on first mount so initial render shows real data,
  // not the loading state.
  if (!hydrated) {
    qc.setQueryData(["conversations"], initialConversations);
    qc.setQueryData(["journal", "today"], {
      entry: initialJournaled ? { id: "hydrated" } : null,
    });
    setHydrated(true);
  }

  // No-op — keeps the lint happy.
  useEffect(() => {}, []);

  return (
    <div className="flex h-screen">
      <Sidebar />
      {children}
    </div>
  );
}
