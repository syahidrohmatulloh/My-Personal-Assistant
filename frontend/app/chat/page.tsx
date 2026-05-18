"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Sparkles } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Conversation,
  getMainConversation,
} from "@/lib/api";

export default function ChatIndexPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const { data: mainChat, isLoading, error } = useQuery({
    queryKey: ["conversations", "main"],
    queryFn: getMainConversation,
    staleTime: 60_000,
    retry: 1,
  });

  useEffect(() => {
    if (!mainChat) return;

    qc.setQueryData<Conversation[]>(["conversations"], (old = []) => {
      const exists = old.some((conversation) => conversation.id === mainChat.id);
      if (exists) {
        return old.map((conversation) =>
          conversation.id === mainChat.id ? { ...conversation, ...mainChat } : conversation,
        );
      }

      return [mainChat, ...old];
    });

    router.replace(`/chat/${mainChat.id}`);
  }, [mainChat, qc, router]);

  if (error) {
    return (
      <main className="flex-1 grid place-items-center px-6">
        <div className="text-center max-w-md fade-up">
          <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-accent shadow-xl shadow-accent/30 mb-5">
            <Sparkles className="h-6 w-6 text-on-accent" strokeWidth={2.2} />
          </div>
          <h1 className="text-2xl sm:text-3xl font-semibold text-fg mb-2 tracking-tighter">
            Could not open Main Chat
          </h1>
          <p className="text-sm sm:text-base text-fg-muted">
            Please refresh the page or start a new chat from the sidebar.
          </p>
        </div>
      </main>
    );
  }

  return (
    <main className="flex-1 grid place-items-center px-4 sm:px-6">
      <div className="text-fg-subtle text-sm">
        {isLoading ? "Opening Main Chat…" : "Redirecting…"}
      </div>
    </main>
  );
}
