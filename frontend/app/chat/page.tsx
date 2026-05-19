"use client";

import { FormEvent, KeyboardEvent, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, CalendarDays, Plus, Sparkles } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createConversation,
  getTodayBriefing,
  getTodaysJournal,
  type Conversation,
} from "@/lib/api";

export default function ChatIndexPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");

  const { data: briefing } = useQuery({
    queryKey: ["briefing", "today"],
    queryFn: getTodayBriefing,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const { data: today } = useQuery({
    queryKey: ["journal", "today"],
    queryFn: getTodaysJournal,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const journaledToday = Boolean(today?.entry);

  const title = useMemo(() => {
    const hour = new Date().getHours();

    if (briefing?.content) {
      return "There’s a thread we can pick up.";
    }

    if (!journaledToday && hour >= 18) {
      return "Want to close the day together?";
    }

    if (hour < 11) {
      return "What should we start with today?";
    }

    if (hour < 17) {
      return "What should we work through first?";
    }

    return "Where do you want to continue?";
  }, [briefing?.content, journaledToday]);

  const createMut = useMutation({
    mutationFn: (message?: string) => createConversation("New chat"),
    onSuccess: (conversation, message) => {
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) => [
        conversation,
        ...old.filter((item) => item.id !== conversation.id),
      ]);

      const text = (message ?? draft).trim();
      if (text) {
        router.push(`/chat/${conversation.id}?prefill=${encodeURIComponent(text)}`);
      } else {
        router.push(`/chat/${conversation.id}`);
      }
    },
  });

  function startChat(message?: string) {
    if (createMut.isPending) return;
    createMut.mutate(message);
  }

  function handleSubmit(event?: FormEvent) {
    event?.preventDefault();
    const text = draft.trim();
    if (!text) return;
    startChat(text);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  return (
    <main className="flex min-h-[calc(100vh-64px)] flex-1 items-center justify-center px-4 sm:px-6">
      <div className="w-full max-w-3xl">
        <div className="mx-auto mb-6 flex flex-col items-center text-center">
          <div className="mb-4 grid h-11 w-11 place-items-center rounded-2xl border border-white/30 bg-white/55 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-white/10 dark:bg-white/8 dark:shadow-black/20">
            <Sparkles className="h-5 w-5 text-slate-900 dark:text-white" strokeWidth={2.2} />
          </div>

          <h1 className="text-2xl font-semibold tracking-tight text-slate-950 sm:text-4xl dark:text-white">
            {title}
          </h1>
        </div>

        {briefing?.content ? (
          <button
            type="button"
            onClick={() => startChat("Let's discuss today's briefing.")}
            disabled={createMut.isPending}
            className="mx-auto mb-3 flex max-w-2xl items-center gap-2 rounded-2xl border border-border bg-fg/[0.035] px-3.5 py-2.5 text-left text-xs text-fg-muted transition hover:bg-fg/5 hover:text-fg disabled:opacity-60"
          >
            <CalendarDays className="h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">
              Today’s briefing is ready — discuss it with Aliyya
            </span>
          </button>
        ) : null}

        <form onSubmit={handleSubmit} className="mx-auto w-full max-w-2xl">
          <div className="rounded-[1.65rem] border border-slate-300/75 bg-white/92 px-3.5 py-3 shadow-[0_8px_28px_rgba(15,23,42,0.07)] backdrop-blur dark:border-white/10 dark:bg-[#111827]/88 dark:shadow-[0_10px_30px_rgba(0,0,0,0.32)]">
            <div className="flex items-end gap-2.5">
              <button
                type="button"
                aria-label="Add"
                className="mb-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-100 dark:text-zinc-200 dark:hover:bg-white/10"
              >
                <Plus className="h-5 w-5" strokeWidth={2.2} />
              </button>

              <div className="min-w-0 flex-1">
                <textarea
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={1}
                  placeholder="Ask Aliyya anything"
                  className="max-h-40 min-h-[42px] w-full resize-none border-0 bg-transparent px-1 py-2.5 text-[0.98rem] leading-6 text-slate-950 outline-none placeholder:text-slate-400 dark:text-white dark:placeholder:text-zinc-500"
                />
              </div>

              <button
                type="submit"
                disabled={createMut.isPending || draft.trim().length === 0}
                aria-label="Start chat"
                className="mb-1 inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-950 text-white transition hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-35 dark:bg-white dark:text-slate-950 dark:hover:bg-zinc-200"
              >
                <ArrowUp className="h-4 w-4" strokeWidth={2.3} />
              </button>
            </div>
          </div>
        </form>

        <div className="mx-auto mt-3 flex max-w-2xl flex-wrap justify-center gap-2">
          {[
            "Plan my day",
            "Reflect on today",
            "Continue from memory",
          ].map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              onClick={() => {
                setDraft(suggestion);
              }}
              className="rounded-full border border-border bg-fg/[0.025] px-3 py-1.5 text-xs text-fg-muted transition hover:bg-fg/5 hover:text-fg"
            >
              {suggestion}
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
