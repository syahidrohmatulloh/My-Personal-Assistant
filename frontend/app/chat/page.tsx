"use client";

import { useRouter } from "next/navigation";
import { Sparkles } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createConversation, type Conversation } from "@/lib/api";

export default function ChatIndexPage() {
  const router = useRouter();
  const qc = useQueryClient();

  const createMut = useMutation({
    mutationFn: () => createConversation("New chat"),
    onSuccess: (conversation) => {
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) => [
        conversation,
        ...old.filter((item) => item.id !== conversation.id),
      ]);
      router.push(`/chat/${conversation.id}`);
    },
  });

  return (
    <main className="flex-1 grid place-items-center px-4 sm:px-6">
      <div className="w-full max-w-xl text-center fade-up">
        <div className="mx-auto mb-5 grid h-14 w-14 place-items-center rounded-2xl bg-accent shadow-xl shadow-accent/25">
          <Sparkles className="h-6 w-6 text-on-accent" strokeWidth={2.25} />
        </div>

        <h1 className="text-2xl sm:text-3xl font-semibold tracking-tighter text-fg">
          Start a new chat
        </h1>

        <p className="mt-2 text-sm sm:text-base text-fg-muted">
          Open a fresh conversation, or choose Main Chat - Aliyya from the sidebar.
        </p>

        <button
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending}
          className="mt-6 inline-flex items-center justify-center rounded-full bg-accent px-5 py-2.5 text-sm font-medium text-on-accent transition hover:bg-accent-hover disabled:opacity-60"
        >
          {createMut.isPending ? "Creating…" : "New chat"}
        </button>
      </div>
    </main>
  );
}
