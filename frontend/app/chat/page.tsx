"use client";

import { FormEvent, KeyboardEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, Plus, Sparkles } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createConversation, type Conversation } from "@/lib/api";

export default function ChatIndexPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");

  const createMut = useMutation({
    mutationFn: () => createConversation("New chat"),
    onSuccess: (conversation) => {
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) => [
        conversation,
        ...old.filter((item) => item.id !== conversation.id),
      ]);

      const text = draft.trim();
      if (text) {
        router.push(`/chat/${conversation.id}?prefill=${encodeURIComponent(text)}`);
      } else {
        router.push(`/chat/${conversation.id}`);
      }
    },
  });

  function handleSubmit(event?: FormEvent) {
    event?.preventDefault();
    if (createMut.isPending) return;
    createMut.mutate();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  return (
    <main className="flex min-h-[calc(100vh-64px)] flex-1 items-center justify-center px-4 sm:px-6">
      <div className="w-full max-w-5xl">
        <div className="mx-auto mb-8 flex flex-col items-center text-center">
          <div className="mb-5 grid h-16 w-16 place-items-center rounded-3xl border border-white/30 bg-white/55 shadow-xl shadow-slate-200/40 backdrop-blur dark:border-white/10 dark:bg-white/8 dark:shadow-black/20">
            <Sparkles className="h-7 w-7 text-slate-900 dark:text-white" strokeWidth={2.2} />
          </div>

          <h1 className="text-3xl font-semibold tracking-tight text-slate-950 sm:text-5xl dark:text-white">
            Where should we begin?
          </h1>
        </div>

        <form onSubmit={handleSubmit} className="mx-auto w-full max-w-[980px]">
          <div className="rounded-[2rem] border border-slate-300/80 bg-white/92 px-5 py-4 shadow-[0_10px_35px_rgba(15,23,42,0.08)] backdrop-blur dark:border-white/10 dark:bg-[#111827]/88 dark:shadow-[0_10px_35px_rgba(0,0,0,0.35)]">
            <div className="flex items-end gap-3">
              <button
                type="button"
                aria-label="Add"
                className="mb-1 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-slate-900 transition hover:bg-slate-100 dark:text-white dark:hover:bg-white/10"
              >
                <Plus className="h-6 w-6" strokeWidth={2.2} />
              </button>

              <div className="min-w-0 flex-1">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  placeholder="Ask anything"
                  className="max-h-48 min-h-[52px] w-full resize-none border-0 bg-transparent px-1 py-3 text-[1.05rem] text-slate-950 outline-none placeholder:text-slate-400 dark:text-white dark:placeholder:text-zinc-500"
                />
              </div>

              <button
                type="submit"
                disabled={createMut.isPending}
                aria-label="Start chat"
                className="mb-1 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-slate-950 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-white dark:text-slate-950 dark:hover:bg-zinc-200"
              >
                <ArrowUp className="h-5 w-5" strokeWidth={2.3} />
              </button>
            </div>
          </div>
        </form>
      </div>
    </main>
  );
}
