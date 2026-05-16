"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Sparkles, Sunrise, ArrowRight } from "lucide-react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Briefing,
  type Conversation,
  getTodayBriefing,
  openBriefing,
} from "@/lib/api";

export default function ChatIndexPage() {
  const router = useRouter();
  const qc = useQueryClient();
  const [opening, setOpening] = useState(false);

  // Briefing fetch — generates if missing on the backend.
  // We don't cache for long because a fresh briefing might be added if the
  // user opens at midnight + 1.
  const { data: briefing, isLoading } = useQuery({
    queryKey: ["briefing", "today"],
    queryFn: getTodayBriefing,
    staleTime: 60_000,
    retry: false, // briefing failure shouldn't break the page
  });

  // Pre-loading state — show nothing while we check, to avoid flicker.
  if (isLoading) {
    return (
      <main className="flex-1 grid place-items-center px-4 sm:px-6">
        <div className="text-fg-subtle text-sm">…</div>
      </main>
    );
  }

  async function handleOpen() {
    if (!briefing || opening) return;
    setOpening(true);
    try {
      const { conversation_id } = await openBriefing(briefing.id);

      // Optimistically prepend the new conversation to the sidebar list.
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) => {
        if (old.some((c) => c.id === conversation_id)) return old;
        return [
          {
            id: conversation_id,
            title: "Morning briefing",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          },
          ...old,
        ];
      });
      router.push(`/chat/${conversation_id}`);
    } catch (err) {
      console.error(err);
      setOpening(false);
    }
  }

  // No briefing — brand new user or no life context yet. Show original empty state.
  if (!briefing) {
    return <EmptyState />;
  }

  return (
    <main className="flex-1 overflow-y-auto">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-8 sm:py-12 fade-up">
        {/* Greeting */}
        <div className="flex items-center gap-2 mb-4 text-fg-muted">
          <Sunrise className="h-4 w-4" />
          <span className="text-xs font-medium uppercase tracking-wider">
            {formatGreetingTimeLabel()}
          </span>
        </div>

        {/* Briefing card */}
        <button
          onClick={handleOpen}
          disabled={opening}
          className="block w-full text-left glass-strong rounded-2xl p-5 sm:p-6 transition-all hover:shadow-xl hover:shadow-accent/10 active:scale-[0.99] disabled:opacity-60 group"
        >
          <p className="text-fg text-[15px] sm:text-base leading-relaxed whitespace-pre-wrap">
            {briefing.content}
          </p>
          <div className="mt-4 flex items-center justify-between text-xs text-fg-muted">
            <span>Tap to continue this thread</span>
            <ArrowRight className="h-3.5 w-3.5 group-hover:translate-x-0.5 transition-transform" />
          </div>
        </button>

        {/* OR start fresh */}
        <div className="mt-8 text-center">
          <p className="text-xs text-fg-subtle mb-2">or</p>
          <Link
            href="#"
            onClick={(e) => {
              e.preventDefault();
              // Trigger sidebar's new-chat flow by following the same path —
              // simplest is to just let the sidebar button do it. We provide
              // a hint here.
            }}
            className="text-sm text-fg-muted hover:text-fg"
          >
            Start a fresh conversation from the sidebar
          </Link>
        </div>
      </div>
    </main>
  );
}

function EmptyState() {
  return (
    <main className="flex-1 grid place-items-center px-6">
      <div className="text-center max-w-md fade-up">
        <div className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-accent shadow-xl shadow-accent/30 mb-5">
          <Sparkles className="h-6 w-6 text-on-accent" strokeWidth={2.2} />
        </div>
        <h1 className="text-2xl sm:text-3xl font-semibold text-fg mb-2 tracking-tighter">
          Start a conversation
        </h1>
        <p className="text-sm sm:text-base text-fg-muted">
          Tap <span className="text-fg font-medium">New chat</span> to begin.
        </p>
      </div>
    </main>
  );
}

function formatGreetingTimeLabel(): string {
  const hour = new Date().getHours();
  if (hour < 5) return "Tonight";
  if (hour < 12) return "Good morning";
  if (hour < 17) return "This afternoon";
  if (hour < 21) return "This evening";
  return "Tonight";
}
