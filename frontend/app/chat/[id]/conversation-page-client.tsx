"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";

import { Composer } from "@/components/chat/composer";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ConversationStyleBadge } from "@/components/chat/conversation-style-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatScroll } from "@/components/chat/use-chat-scroll";
import { useChatMessageLoader } from "@/components/chat/use-chat-message-loader";
import { useChatStreamSender } from "@/components/chat/use-chat-stream-sender";

import {
  getIdentity,
  getMainConversation,
  type ChatStreamMeta,
  type Message,
} from "@/lib/api";

import {
  buildUiContextSnapshot,
  coerceBackgroundSettings,
  readBackgroundSettings,
  saveBackgroundSettings,
} from "@/lib/ambient-background";

import {
  hydrateCompanionMoodForConversation,
} from "@/lib/companion-mood";
import { subscribeCompanionMoodRealtime } from "@/lib/companion-mood-realtime";


type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string };

export function ConversationPageClient({
  conversationId,
  initialMessages = [],
}: {
  conversationId: string
  initialMessages?: Message[]
}) {
  const router = useRouter();
  const searchParams = useSearchParams();

  const [messages, setMessages] = useState<LocalMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(initialMessages.length === 0);
  const [historySettled, setHistorySettled] = useState(initialMessages.length === 0);
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

  const consumedPrefillRef = useRef<string | null>(null);
  const {
    scrollRef,
    stickToBottomRef,
    showJumpBtn,
    jumpToBottom,
    settleScrollAfterPaint,
    markShouldStickToBottom,
  } = useChatScroll({
    messageCount: messages.length,
    followSignal: messages,
  });

  useChatMessageLoader({
    conversationId,
    initialMessages,
    setMessages,
    setLoading,
    setHistorySettled,
    markShouldStickToBottom,
    settleScrollAfterPaint,
  });

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


  const handleSend = useChatStreamSender({
    conversationId,
    input,
    setInput,
    sending,
    setSending,
    messagesLength: messages.length,
    setMessages,
    setStreamMeta,
    markShouldStickToBottom,
  });

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

      <Composer
        value={input}
        onChange={setInput}
        onSubmit={handleSend}
        disabled={sending}
      />
    </main>
  );
}
