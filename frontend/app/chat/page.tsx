"use client";

import { FormEvent, KeyboardEvent, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowUp, CalendarDays, Plus, Sparkles } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createConversation,
  getIdentity,
  getTodayBriefing,
  getTodaysJournal,
  listGoals,
  startBriefingConversation,
  type Conversation,
} from "@/lib/api";


function formatShortDate(value: unknown): string | null {
  if (!value || typeof value !== "string") return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function daysUntilNextAnnualDate(value: unknown): number | null {
  if (!value || typeof value !== "string") return null;

  const source = new Date(value);
  if (Number.isNaN(source.getTime())) return null;

  const today = new Date();
  const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
  const thisYear = new Date(today.getFullYear(), source.getMonth(), source.getDate());
  const next =
    thisYear >= todayDate
      ? thisYear
      : new Date(today.getFullYear() + 1, source.getMonth(), source.getDate());

  return Math.round((next.getTime() - todayDate.getTime()) / 86400000);
}

function uniqueShortTitles(items: Array<string | null | undefined>): string[] {
  const seen = new Set<string>();
  const result: string[] = [];

  for (const item of items) {
    const text = String(item || "").trim();
    if (!text) continue;
    if (text.length > 72) continue;

    const key = text.toLowerCase();
    if (seen.has(key)) continue;

    seen.add(key);
    result.push(text);
  }

  return result.slice(0, 6);
}


export default function ChatIndexPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [draft, setDraft] = useState("");

  const { data: briefing, isLoading: briefingLoading } = useQuery({
    queryKey: ["briefing", "today"],
    queryFn: getTodayBriefing,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const { data: today, isLoading: journalLoading } = useQuery({
    queryKey: ["journal", "today"],
    queryFn: getTodaysJournal,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const { data: goals = [], isLoading: goalsLoading } = useQuery({
    queryKey: ["goals", "chat-home-title"],
    queryFn: () => listGoals("active"),
    staleTime: 60 * 1000,
    retry: false,
  });

  const { data: identity, isLoading: identityLoading } = useQuery({
    queryKey: ["identity", "chat-home-title"],
    queryFn: getIdentity,
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  const journaledToday = Boolean(today?.entry);
  const assistantName =
    typeof identity?.profile?.assistant_name === "string" &&
    identity.profile.assistant_name.trim().length > 0
      ? identity.profile.assistant_name.trim()
      : "your assistant";

  const initialTitleReady =
    !briefingLoading && !journalLoading && !goalsLoading && !identityLoading;

  const titleOptions = useMemo(() => {
    const hour = new Date().getHours();
    const activeGoals = Array.isArray(goals)
      ? goals.filter((goal) => goal?.status === "active" || !goal?.status)
      : [];
    const firstGoal = activeGoals[0];
    const birthdayDays = daysUntilNextAnnualDate(identity?.profile?.birthday);
    const birthdayDate = formatShortDate(identity?.profile?.birthday);

    return uniqueShortTitles([
      briefing?.content ? "There’s a thread we can pick up" : null,
      firstGoal?.title ? `A goal is waiting: ${firstGoal.title}` : null,
      activeGoals.length > 1 ? `${activeGoals.length} active goals in motion` : null,
      birthdayDays === 0 ? "There’s something special today" : null,
      birthdayDays === 1 ? "A special date is tomorrow" : null,
      birthdayDays !== null && birthdayDays > 1 && birthdayDays <= 14 && birthdayDate
        ? `A special date is coming on ${birthdayDate}`
        : null,
      !journaledToday && hour >= 18 ? "Want to close the day together?" : null,
      hour < 11 ? "What should we start with today?" : null,
      hour >= 11 && hour < 17 ? "What should we work through first?" : null,
      "Where do you want to continue",
    ]);
  }, [briefing?.content, goals, identity?.profile?.birthday, journaledToday]);

  const titleSignature = titleOptions.join("|");
  const [title, setTitle] = useState("Where do you want to continue");

  useEffect(() => {
    if (!initialTitleReady || titleOptions.length === 0) {
      setTitle("Where do you want to continue");
      return;
    }

    let nextIndex = 0;

    const timer = window.setInterval(() => {
      setTitle(titleOptions[nextIndex] || "Where do you want to continue");
      nextIndex = (nextIndex + 1) % titleOptions.length;
    }, 5000);

    return () => window.clearInterval(timer);
  }, [initialTitleReady, titleOptions.length, titleSignature]);

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

  const startBriefingMut = useMutation({
    mutationFn: (briefingId: string) => startBriefingConversation(briefingId),
    onSuccess: (result) => {
      router.push(`/chat/${result.conversation_id}`);
    },
  });

  function startChat(message?: string) {
    if (createMut.isPending) return;
    const text = (message ?? draft).trim();
    if (!text) return;
    createMut.mutate(text);
  }

  function handleSubmit(event?: FormEvent) {
    event?.preventDefault();
    startChat();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSubmit();
    }
  }

  const suggestions = [
    {
      label: "Plan my day",
      prompt:
        "Help me plan my day based on what you know about my priorities, recent context, and current energy. Make it practical and not too long.",
    },
    {
      label: "Reflect on today",
      prompt:
        "Help me reflect on today. Ask me a few thoughtful questions first if you need more context, then help me turn it into a useful journal-style reflection.",
    },
    {
      label: "Continue from memory",
      prompt:
        "Continue from what matters most in my recent memory and conversations. Pick the most useful thread to continue, explain why, then suggest the next step.",
    },
  ];

  return (
    <main className="flex min-h-[calc(100vh-64px)] flex-1 items-center justify-center px-4 sm:px-6">
      <div className="w-full max-w-3xl">
        <div className="mx-auto mb-6 flex flex-col items-center text-center">
          <div className="mb-4 grid h-11 w-11 place-items-center rounded-2xl border border-white/30 bg-white/55 shadow-lg shadow-slate-200/40 backdrop-blur dark:border-white/10 dark:bg-white/8 dark:shadow-black/20">
            <Sparkles className="h-5 w-5 text-slate-900 dark:text-white" strokeWidth={2.2} />
          </div>

          <h1 className="text-2xl font-semibold tracking-tight text-fg sm:text-4xl">
            {title}
          </h1>
        </div>

        {briefingLoading ? (
          <button
            type="button"
            disabled
            aria-live="polite"
            className="mx-auto mb-3 flex max-w-2xl items-center gap-2 rounded-2xl border border-border bg-fg/[0.025] px-3.5 py-2.5 text-left text-xs text-fg-muted opacity-70"
          >
            <CalendarDays className="h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">Checking today’s briefing</span>
          </button>
        ) : briefing?.content ? (
          <button
            type="button"
            onClick={() => briefing?.id && startBriefingMut.mutate(briefing.id)}
            disabled={createMut.isPending || startBriefingMut.isPending}
            className="mx-auto mb-3 flex max-w-2xl items-center gap-2 rounded-2xl border border-border bg-fg/[0.035] px-3.5 py-2.5 text-left text-xs text-fg-muted transition hover:bg-fg/5 hover:text-fg disabled:opacity-60"
          >
            <CalendarDays className="h-4 w-4 shrink-0" />
            <span className="min-w-0 flex-1 truncate">
              {briefing.opened_at || briefing.conversation_id
                ? "Want to revisit today’s briefing?"
                : `Today’s briefing is ready — discuss it with ${assistantName}`}
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
                  placeholder={`Ask ${assistantName} anything`}
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
          {suggestions.map((suggestion) => (
            <button
              key={suggestion.label}
              type="button"
              disabled={createMut.isPending || startBriefingMut.isPending}
              onClick={() => startChat(suggestion.prompt)}
              className="rounded-full border border-border bg-fg/[0.025] px-3 py-1.5 text-xs text-fg-muted transition hover:bg-fg/5 hover:text-fg disabled:opacity-60"
            >
              {suggestion.label}
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}
