"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowRight, Sunrise, X } from "lucide-react";

import { Composer } from "@/components/chat/composer";
import { TypingIndicator } from "@/components/chat/typing-indicator";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ConversationStyleBadge } from "@/components/chat/conversation-style-badge";
import { Skeleton } from "@/components/ui/skeleton";

import {
  getIdentity,
  getMainConversation,
  getTodayBriefing,
  openBriefing,
  listMessages,
  streamChat,
  type Briefing,
  type ChatStreamMeta,
  type Identity,
  type Conversation,
  type Message,
} from "@/lib/api";

import {
  buildUiContextSnapshot,
  coerceBackgroundSettings,
  readBackgroundSettings,
  saveBackgroundSettings,
  setBackgroundMoodHint,
} from "@/lib/ambient-background";

import {
  hydrateCompanionMoodForConversation,
  updateCompanionMoodFromMessage,
  shouldDeferCompanionMoodToAssistant,
  setPendingCompanionMoodSimulation,
  updateCompanionMoodFromAssistantText,
  shouldRespectCompanionMoodOverride,
} from "@/lib/companion-mood";
import { subscribeCompanionMoodRealtime } from "@/lib/companion-mood-realtime";


type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string };

const STICK_THRESHOLD = 120;

// Helper — scroll the *specific* container to bottom deterministically.
// Using element.scrollTop avoids scrollIntoView's quirks where it can
// scroll the wrong ancestor when overflow-hidden is in the chain.
function scrollContainerToBottom(el: HTMLDivElement | null, smooth = false) {
  if (!el) return;
  if (smooth) {
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  } else {
    el.scrollTop = el.scrollHeight;
  }
}

function BriefingDock({
  briefing,
  expanded,
  onToggle,
  onDiscuss,
  onDismiss,
}: {
  briefing: Briefing
  expanded: boolean
  onToggle: () => void
  onDiscuss: () => void
  onDismiss: () => void
}) {
  return (
    <section className="shrink-0 border-t border-border bg-bg/70 px-3 py-2 backdrop-blur-xl sm:px-6">
      <div className="mx-auto max-w-3xl rounded-2xl border border-border bg-fg/[0.035] p-3 shadow-sm">
        <div className="flex items-center justify-between gap-3">
          <button
            onClick={onToggle}
            className="min-w-0 flex-1 text-left"
          >
            <div className="flex items-center gap-2 text-fg">
              <Sunrise className="h-4 w-4 shrink-0 text-fg-muted" />
              <span className="truncate text-sm font-medium">
                Today&apos;s briefing is ready
              </span>
            </div>
            <p className="mt-0.5 text-xs text-fg-muted">
              View it here without adding it to your chat history.
            </p>
          </button>

          <div className="flex shrink-0 items-center gap-1.5">
            <button
              onClick={onToggle}
              className="rounded-full border border-border px-3 py-1.5 text-xs font-medium text-fg-muted transition hover:bg-fg/5 hover:text-fg"
            >
              {expanded ? "Hide" : "View"}
            </button>
            <button
              onClick={onDismiss}
              className="rounded-full p-1.5 text-fg-subtle transition hover:bg-fg/5 hover:text-fg"
              aria-label="Dismiss briefing"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        </div>

        {expanded ? (
          <div className="mt-3 border-t border-border pt-3">
            <p className="whitespace-pre-wrap text-sm leading-6 text-fg">
              {briefing.content}
            </p>

            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <button
                onClick={onDiscuss}
                className="inline-flex items-center justify-center gap-2 rounded-full bg-accent px-4 py-2 text-sm font-medium text-on-accent transition hover:bg-accent-hover"
              >
                Discuss briefing
                <ArrowRight className="h-4 w-4" />
              </button>

              <Link
                href="/memories"
                className="inline-flex items-center justify-center rounded-full border border-border px-4 py-2 text-sm font-medium text-fg-muted transition hover:bg-fg/5 hover:text-fg"
              >
                Open Memories Review
              </Link>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  )
}

export function ConversationPageClient({ conversationId }: { conversationId: string }) {
  const qc = useQueryClient();

  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showJumpBtn, setShowJumpBtn] = useState(false);
  const [streamMeta, setStreamMeta] = useState<ChatStreamMeta | null>(null);

  const { data: identity } = useQuery({
    queryKey: ["identity"],
    queryFn: getIdentity,
    staleTime: 5 * 60 * 1000,
    gcTime: 30 * 60 * 1000,
    refetchOnMount: false,
    refetchOnWindowFocus: false,
  });

  const assistantName =
    streamMeta?.assistant_name ||
    (typeof identity?.profile?.assistant_name === "string" &&
    identity.profile.assistant_name.trim().length > 0
      ? identity.profile.assistant_name.trim()
      : "Aliyya");

  const { data: mainChat } = useQuery({
    queryKey: ["conversations", "main"],
    queryFn: getMainConversation,
    staleTime: 60_000,
    retry: 1,
  });

  const isMainChat = mainChat?.id === conversationId;

  const { data: briefing } = useQuery({
    queryKey: ["briefing", "today"],
    queryFn: getTodayBriefing,
    staleTime: 60_000,
    retry: false,
    enabled: isMainChat,
  });


const [briefingDismissed, setBriefingDismissed] = useState(false);
  const [briefingPanelOpen, setBriefingPanelOpen] = useState(false);
  const [briefingDismissalLoaded, setBriefingDismissalLoaded] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);

  const applyAssistantMoodAfterLatestMessagePaint = useCallback(
    (assistantText: string) => {
      // Let the final assistant bubble render first, then update ambience.
      // This prevents the mood shift from feeling like it was triggered by the user's previous message.
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          window.setTimeout(() => {
            updateCompanionMoodFromAssistantText(assistantText, conversationId);
          }, 350);
        });
      });
    },
    [conversationId],
  );

  useEffect(() => {
    let unsubscribe: (() => void) | null = null;
    let cancelled = false;

    void hydrateCompanionMoodForConversation(conversationId);

    subscribeCompanionMoodRealtime(conversationId).then((fn) => {
      if (cancelled) {
        fn();
        return;
      }
      unsubscribe = fn;
    });

    return () => {
      cancelled = true;
      if (unsubscribe) unsubscribe();
    };
  }, [conversationId]);

  useEffect(() => {
    const savedSettings = identity?.profile?.background_settings;

    if (!savedSettings) return;

    const mergedSettings = coerceBackgroundSettings(
      savedSettings,
      readBackgroundSettings(),
    );

    saveBackgroundSettings(mergedSettings);

    window.dispatchEvent(
      new CustomEvent("assistant.background.settings.changed", {
        detail: { reason: "identity-background-sync" },
      }),
    );
  }, [identity]);


  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(
        "assistant.lastChatPath",
        window.location.pathname,
      );
    }
  }, [conversationId]);

  useEffect(() => {
    if (!briefing) {
      setBriefingDismissed(false);
      setBriefingPanelOpen(false);
      setBriefingDismissalLoaded(true);
      return;
    }

    const dismissed =
      typeof window !== "undefined" &&
      window.localStorage.getItem(briefingDismissKey(briefing)) === "true";

    setBriefingDismissed(dismissed);
    setBriefingPanelOpen(false);
    setBriefingDismissalLoaded(true);
  }, [briefing?.id]);

  // Load messages, then scroll the container to bottom on next frame.
  useEffect(() => {
    let cancelled = false;

    setLoading(true);
    stickToBottomRef.current = true;

    listMessages(conversationId)
      .then((msgs) => {
        if (cancelled) return;

        setMessages(msgs);

        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            scrollContainerToBottom(scrollRef.current);
          });
        });
      })
      .catch(console.error)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // Detect whether user is near the bottom — affects auto-follow during stream.
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    function onScroll() {
      const distance = el!.scrollHeight - el!.scrollTop - el!.clientHeight;
      const nearBottom = distance < STICK_THRESHOLD;
      stickToBottomRef.current = nearBottom;
      setShowJumpBtn(!nearBottom && messages.length > 0);
    }
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [messages.length]);

  // Auto-follow new content only if user is near bottom.
  useEffect(() => {
    if (!stickToBottomRef.current) return;
    scrollContainerToBottom(scrollRef.current);
  }, [messages]);

  function jumpToBottom() {
    scrollContainerToBottom(scrollRef.current, true);
    stickToBottomRef.current = true;
    setShowJumpBtn(false);
  }

  function briefingDismissKey(briefing: Briefing) {
    return `assistant.briefing.dismissed.${briefing.id}`;
  }

  function dismissBriefing(briefing: Briefing) {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(briefingDismissKey(briefing), "true");
    }

    setBriefingDismissed(true);
    setBriefingPanelOpen(false);
  }

  async function prepareBriefingDiscussion(briefing: Briefing) {
    try {
      await openBriefing(briefing.id)
    } catch (err) {
      console.error(err)
    }

    setInput("Let's discuss today's briefing.")
    dismissBriefing(briefing)
  }

  const handleSend = useCallback(
    async (attachmentIds: string[] = []) => {
      const text = input.trim();
      if (shouldDeferCompanionMoodToAssistant(text)) {
        setPendingCompanionMoodSimulation(text, conversationId);
      } else {
        updateCompanionMoodFromMessage(text, conversationId);
      }
      const hasContent = text.length > 0 || attachmentIds.length > 0;
      if (!hasContent || sending) return;

      // If there are attachments but no text, send a neutral placeholder so the
      // backend always has at least one text block in the user content array.
      const messageText = text || (attachmentIds.length > 0 ? "(shared an attachment)" : "");

      setInput("");
      setSending(true);
      setStreamMeta(null);
      stickToBottomRef.current = true;

      const wasFirstMessage = messages.length === 0;

      const userMsg: LocalMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content: messageText,
        created_at: new Date().toISOString(),
      };
    const assistantId = `local-asst-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: "assistant", content: "", pending: true },
    ]);

    if (wasFirstMessage) {
      const title = messageText.slice(0, 40) + (messageText.length > 40 ? "…" : "");
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.map((c) => (c.id === conversationId ? { ...c, title } : c)),
      );
    }

    let assistantText = "";
    let pending = "";
    let rafId: number | null = null;
    const flush = () => {
      if (!pending) {
        rafId = null;
        return;
      }
      assistantText += pending;
      pending = "";
      const snapshot = assistantText;
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? { id: assistantId, role: "assistant", content: snapshot, pending: true }
            : m,
        ),
      );
      rafId = null;
    };

    try {
      for await (const event of streamChat(conversationId, messageText, attachmentIds)) {
        if (event.type === "meta") {
          setStreamMeta(event);
          if (event.assistant_name) {
            qc.setQueryData<Identity | undefined>(["identity"], (old) => ({
              profile: { ...(old?.profile ?? {}), assistant_name: event.assistant_name },
              narrative: old?.narrative ?? null,
              updated_at: old?.updated_at ?? null,
            }));
          }
          if ((event.mood || event.background_palette_hint) && !shouldRespectCompanionMoodOverride(event.mood)) {
            setBackgroundMoodHint({
              mood: event.mood,
              palette: event.background_palette_hint as any,
            });
          }
          continue;
        }
        if (event.type === "done") continue;

        pending += event.text;
        if (rafId == null) {
          rafId = requestAnimationFrame(flush);
        }
      }
      if (rafId != null) cancelAnimationFrame(rafId);
      flush();

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                id: assistantId,
                role: "assistant",
                content: assistantText,
                created_at: new Date().toISOString(),
              }
            : m,
        ),
      );

      applyAssistantMoodAfterLatestMessagePaint(assistantText);

      // Background title generation on the server runs after the stream
      // closes. Wait a moment so the refetch picks up the real title.
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["conversations"] });
      }, 4000);
    } catch (err) {
      console.error(err);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                id: assistantId,
                role: "assistant",
                content: `**Error:** ${err instanceof Error ? err.message : "unknown"}`,
                created_at: new Date().toISOString(),
              }
            : m,
        ),
      );
    } finally {
      setSending(false);
      setStreamMeta(null);
    }
  }, [conversationId, input, messages.length, qc, sending]);

  return (
    <main className="flex-1 flex flex-col min-w-0 min-h-0 relative">
      <ConversationStyleBadge conversationId={conversationId} />
<div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto scroll-smooth-mobile overscroll-contain"
      >
        <div className="max-w-3xl mx-auto px-3 sm:px-6 py-4 sm:py-6 space-y-3 sm:space-y-4">
          {loading ? (
            <>
              <Skeleton className="h-12 w-3/4 ml-auto rounded-2xl" />
              <Skeleton className="h-20 w-4/5 rounded-2xl" />
              <Skeleton className="h-10 w-2/3 ml-auto rounded-2xl" />
            </>
          ) : messages.length === 0 ? (
            <p className="text-sm text-fg-muted text-center pt-12">
              Say hello — I&apos;m listening.
            </p>
          ) : (
            messages.map((m) => (
              <MessageBubble
                key={m.id}
                role={m.role}
                content={m.content}
                pending={"pending" in m && m.pending === true}
              />
            ))
          )}
        </div>
      </div>

      {showJumpBtn && (
        <button
          onClick={jumpToBottom}
          className="absolute bottom-[calc(env(safe-area-inset-bottom)+88px)] sm:bottom-24 left-1/2 -translate-x-1/2 glass-strong h-9 px-3 rounded-full text-xs font-medium text-fg flex items-center gap-1.5 shadow-ds-md fade-up"
          aria-label="Jump to latest"
        >
          <ArrowDown className="h-3.5 w-3.5" />
          Jump to latest
        </button>
      )}

{isMainChat && briefing && briefingDismissalLoaded && !briefingDismissed ? (
        <BriefingDock
          briefing={briefing}
          expanded={briefingPanelOpen}
          onToggle={() => setBriefingPanelOpen((value) => !value)}
          onDiscuss={() => void prepareBriefingDiscussion(briefing)}
          onDismiss={() => dismissBriefing(briefing)}
        />
      ) : null}

      <TypingIndicator visible={sending} assistantName={assistantName} />

      <Composer
        value={input}
        onChange={setInput}
        onSubmit={handleSend}
        disabled={sending}
      />
    </main>
  );
}
