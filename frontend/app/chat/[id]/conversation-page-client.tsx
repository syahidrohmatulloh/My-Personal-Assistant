"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";

import { Composer } from "@/components/chat/composer";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ConversationStyleBadge } from "@/components/chat/conversation-style-badge";
import { Skeleton } from "@/components/ui/skeleton";

import {
  getIdentity,
  getMainConversation,
  listMessages,
  streamChat,
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

const CHAT_MESSAGES_CACHE_PREFIX = "app:chat-messages-cache:";

type CachedChatPayload = {
  version: 1;
  savedAt: string;
  messages: Message[];
};

function chatCacheKey(conversationId: string): string {
  return `${CHAT_MESSAGES_CACHE_PREFIX}${conversationId}`;
}

function isCacheableMessage(value: unknown): value is Message {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false;
  }

  const item = value as Partial<Message>;

  return (
    typeof item.id === "string" &&
    (item.role === "user" || item.role === "assistant") &&
    typeof item.content === "string"
  );
}

function readCachedMessages(conversationId: string): Message[] {
  if (typeof window === "undefined") {
    return [];
  }

  const raw = window.localStorage.getItem(chatCacheKey(conversationId));
  if (!raw) {
    return [];
  }

  try {
    const parsed = JSON.parse(raw) as Partial<CachedChatPayload>;
    return Array.isArray(parsed.messages)
      ? parsed.messages.filter(isCacheableMessage)
      : [];
  } catch {
    return [];
  }
}

function writeCachedMessages(conversationId: string, messages: LocalMessage[]) {
  if (typeof window === "undefined") {
    return;
  }

  const cacheable = messages.filter((message): message is Message => {
    if ("pending" in message && message.pending === true) {
      return false;
    }

    return (
      typeof message.id === "string" &&
      (message.role === "user" || message.role === "assistant") &&
      typeof message.content === "string"
    );
  });

  const payload: CachedChatPayload = {
    version: 1,
    savedAt: new Date().toISOString(),
    messages: cacheable.slice(-120),
  };

  try {
    window.localStorage.setItem(chatCacheKey(conversationId), JSON.stringify(payload));
  } catch {
    // Ignore storage quota or privacy-mode failures.
  }
}


// Helper — scroll the *specific* container to bottom deterministically.
// Using element.scrollTop avoids scrollIntoView's quirks where it can
// scroll the wrong ancestor when overflow-hidden is in the chain.
function scrollContainerToBottom(el: HTMLDivElement | null, smooth = false) {
  if (!el) return;
  if (smooth) {
    el.scrollTo({ top: el.scrollHeight, behavior: "auto" });
  } else {
    el.scrollTop = el.scrollHeight;
  }
}

export function ConversationPageClient({
  conversationId,
  initialMessages = [],
}: {
  conversationId: string
  initialMessages?: Message[]
}) {
  const qc = useQueryClient();
  const router = useRouter();
  const searchParams = useSearchParams();

  const [messages, setMessages] = useState<LocalMessage[]>(() =>
    initialMessages.length > 0 ? initialMessages : readCachedMessages(conversationId),
  );
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(initialMessages.length === 0);
  const [historySettled, setHistorySettled] = useState(initialMessages.length === 0);
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
      : "Assistant");

  const { data: mainChat } = useQuery({
    queryKey: ["conversations", "main"],
    queryFn: getMainConversation,
    staleTime: 60_000,
    retry: 1,
  });

  const isMainChat = mainChat?.id === conversationId;

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickToBottomRef = useRef(true);
  const consumedPrefillRef = useRef<string | null>(null);

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


  // Load messages, then scroll the container to bottom on next frame.
  // Server-prefetched messages make direct opens much faster. The client fetch
  // is only a fallback for cases where no initial messages were provided.
  useEffect(() => {
    let cancelled = false;

    const cachedMessages = readCachedMessages(conversationId);

    setLoading(initialMessages.length === 0);
    setHistorySettled(false);
    stickToBottomRef.current = true;

    const settleAfterPaint = () => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (cancelled) return;
          scrollContainerToBottom(scrollRef.current);
          setHistorySettled(true);
        });
      });
    };

    if (initialMessages.length > 0) {
      setMessages(initialMessages);
      writeCachedMessages(conversationId, initialMessages);
      setLoading(false);
      settleAfterPaint();

      return () => {
        cancelled = true;
      };
    }

    if (cachedMessages.length > 0) {
      setMessages(cachedMessages);
      settleAfterPaint();
    }

    listMessages(conversationId)
      .then((msgs) => {
        if (cancelled) return;

        setMessages(msgs);
        writeCachedMessages(conversationId, msgs);
        setLoading(false);
        settleAfterPaint();
      })
      .catch((err) => {
        console.error(err);
        if (!cancelled) {
          setLoading(false);
          setHistorySettled(true);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [conversationId, initialMessages]);

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

const handleSend = useCallback(
    async (attachmentIds: string[] = [], overrideText?: string) => {
      const text = (overrideText ?? input).trim();
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
    setMessages((prev) => {
      const next: LocalMessage[] = [
        ...prev,
        userMsg,
        { id: assistantId, role: "assistant", content: "", pending: true },
      ];
      writeCachedMessages(conversationId, next);
      return next;
    });

    if (wasFirstMessage) {
      const title = messageText.slice(0, 40) + (messageText.length > 40 ? "…" : "");
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.map((c) => (c.id === conversationId ? { ...c, title } : c)),
      );
    }

    let assistantText = "";
    let pending = "";
    let rafId: number | null = null;
    const minThinkingMs = 650;
    const thinkingStartedAt = Date.now();
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

        if (Date.now() - thinkingStartedAt < minThinkingMs) {
          continue;
        }

        if (rafId == null) {
          rafId = requestAnimationFrame(flush);
        }
      }
      const remainingThinkingMs = minThinkingMs - (Date.now() - thinkingStartedAt);
      if (remainingThinkingMs > 0) {
        await new Promise((resolve) => window.setTimeout(resolve, remainingThinkingMs));
      }

      if (rafId != null) cancelAnimationFrame(rafId);
      flush();

      setMessages((prev) => {
        const next: LocalMessage[] = prev.map((m) =>
          m.id === assistantId
            ? {
                id: assistantId,
                role: "assistant",
                content: assistantText,
                created_at: new Date().toISOString(),
              }
            : m,
        );
        writeCachedMessages(conversationId, next);
        return next;
      });

      applyAssistantMoodAfterLatestMessagePaint(assistantText);

      // Background title generation on the server runs after the stream
      // closes. Wait a moment so the refetch picks up the real title.
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["conversations"] });
      }, 4000);
    } catch (err) {
      console.error(err);
      setMessages((prev) => {
        const next: LocalMessage[] = prev.map((m) =>
          m.id === assistantId
            ? {
                id: assistantId,
                role: "assistant",
                content: `**Error:** ${err instanceof Error ? err.message : "unknown"}`,
                created_at: new Date().toISOString(),
              }
            : m,
        );
        writeCachedMessages(conversationId, next);
        return next;
      });
    } finally {
      setSending(false);
      setStreamMeta(null);
    }
  }, [conversationId, input, messages.length, qc, sending]);


  // Calendar handoff: fill the composer with a scheduling-help draft from /calendar.
  useEffect(() => {
    if (typeof window === "undefined") return
    if (loading || sending) return
    if (input.trim().length > 0) return

    const key = "app:calendar-chat-handoff-draft"
    const draft = window.localStorage.getItem(key)?.trim()

    if (!draft) return

    window.localStorage.removeItem(key)
    setInput(draft)
  }, [input, loading, sending])

  // Auto-send a landing-page prefill once when a new conversation is opened.
  useEffect(() => {
    const prefill = searchParams.get("prefill")?.trim();

    if (!prefill) return;
    if (loading || sending) return;
    if (consumedPrefillRef.current === prefill) return;
    if (messages.length > 0) return;

    consumedPrefillRef.current = prefill;
    setInput(prefill);

    void handleSend([], prefill);

    const nextParams = new URLSearchParams(searchParams.toString());
    nextParams.delete("prefill");
    const qs = nextParams.toString();
    router.replace(qs ? `/chat/${conversationId}?${qs}` : `/chat/${conversationId}`, {
      scroll: false,
    });
  }, [
    conversationId,
    handleSend,
    loading,
    messages.length,
    router,
    searchParams,
    sending,
  ]);

  return (
    <main className="flex-1 flex flex-col min-w-0 min-h-0 relative">
      <ConversationStyleBadge conversationId={conversationId} />
<div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain"
      >
        <div
          className={[
            "max-w-3xl mx-auto px-3 sm:px-6 py-4 sm:py-6 space-y-3 sm:space-y-4",
            !loading && messages.length > 0 && !historySettled ? "opacity-0" : "opacity-100",
          ].join(" ")}
        >
          {loading && messages.length > 0 ? (
            <div className="mx-auto mb-2 w-fit rounded-full border border-border bg-bg/80 px-3 py-1 text-[11px] text-fg-muted shadow-sm">
              Showing cached chat while refreshing…
            </div>
          ) : null}

          {loading && messages.length === 0 ? (
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

      <Composer
        value={input}
        onChange={setInput}
        onSubmit={handleSend}
        disabled={sending}
      />
    </main>
  );
}
