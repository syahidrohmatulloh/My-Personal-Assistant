"use client";

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";

import { Composer } from "@/components/chat/composer";
import { ChatMessageList } from "@/components/chat/chat-message-list";
import dynamic from "next/dynamic";

const LazyConversationStyleBadge = dynamic(
  () =>
    import("@/components/chat/conversation-style-badge").then((mod) => ({
      default: mod.ConversationStyleBadge,
    })),
  {
    ssr: false,
    loading: () => null,
  },
);

import { useChatScroll } from "@/components/chat/use-chat-scroll";
import { useChatMessageLoader } from "@/components/chat/use-chat-message-loader";
import { useChatStreamSender } from "@/components/chat/use-chat-stream-sender";
import { useChatRuntimeEffects } from "@/components/chat/use-chat-runtime-effects";
import { useChatPrefill } from "@/components/chat/use-chat-prefill";

import {
  getIdentity,
  listMessages,
  type ChatStreamMeta,
  type Message,
} from "@/lib/api";



type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string };

function localMessageTime(message: LocalMessage) {
  if (!message.created_at) return Number.MAX_SAFE_INTEGER;
  const time = new Date(message.created_at).getTime();
  return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time;
}

function sortLocalMessages(a: LocalMessage, b: LocalMessage) {
  const diff = localMessageTime(a) - localMessageTime(b);
  if (diff !== 0) return diff;
  return String(a.id).localeCompare(String(b.id));
}

function isNearDuplicateMessage(a: LocalMessage, b: LocalMessage) {
  if (a.role !== b.role) return false;
  if (a.content.trim() !== b.content.trim()) return false;

  const aTime = localMessageTime(a);
  const bTime = localMessageTime(b);

  if (aTime === Number.MAX_SAFE_INTEGER || bTime === Number.MAX_SAFE_INTEGER) {
    return true;
  }

  return Math.abs(aTime - bTime) <= 10_000;
}

export function ConversationPageClient({
  conversationId,
  initialMessages = [],
  initialIsMainChat = false,
  initialHasMoreMessages = false,
  initialStyleProfileId = null,
  initialStyleProfileName = null,
}: {
  conversationId: string
  initialMessages?: Message[]
  initialIsMainChat?: boolean
  initialHasMoreMessages?: boolean
  initialStyleProfileId?: string | null
  initialStyleProfileName?: string | null
}) {

  const [messages, setMessages] = useState<LocalMessage[]>(initialMessages);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(initialMessages.length === 0);
  const [historySettled, setHistorySettled] = useState(initialMessages.length === 0);
  const [streamMeta, setStreamMeta] = useState<ChatStreamMeta | null>(null);
  const [showStyleBadge, setShowStyleBadge] = useState(false);

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

  const isMainChat = initialIsMainChat;

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

  const {
    hasMoreMessages,
    loadingEarlier,
    loadEarlierMessages,
  } = useChatMessageLoader({
    conversationId,
    initialMessages,
    initialHasMoreMessages,
    scrollRef,
    setMessages,
    setLoading,
    setHistorySettled,
    markShouldStickToBottom,
    settleScrollAfterPaint,
    liveRefreshEnabled: false,
  });

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

  useChatRuntimeEffects({
    conversationId,
    identity,
  });

  useChatPrefill({
    conversationId,
    input,
    setInput,
    loading,
    sending,
    messagesLength: messages.length,
    handleSend,
  });

  useEffect(() => {
    let cancelled = false;
    let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
    let inFlight = false;

    const pollLatest = async () => {
      if (cancelled) return;

      if (sending || loading || inFlight) {
        timeoutHandle = setTimeout(pollLatest, 3000);
        return;
      }

      inFlight = true;

      try {
        const latest = await listMessages(conversationId, { limit: 80 });
        if (cancelled || latest.length === 0) return;

        let added = false;

        setMessages((current) => {
          const existingIds = new Set(current.map((message) => message.id));
          const incoming = latest.filter((message) => {
            if (existingIds.has(message.id)) return false;
            return !current.some((existing) => isNearDuplicateMessage(existing, message));
          });

          if (incoming.length === 0) {
            return current;
          }

          added = true;
          return [...current, ...incoming].sort(sortLocalMessages);
        });

        if (added) {
          markShouldStickToBottom();
          settleScrollAfterPaint(() => !cancelled);
        }
      } catch (error) {
        console.error("chat heartbeat refresh failed", error);
      } finally {
        inFlight = false;
        if (!cancelled) {
          timeoutHandle = setTimeout(pollLatest, 3000);
        }
      }
    };

    timeoutHandle = setTimeout(pollLatest, 1000);

    return () => {
      cancelled = true;
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
    };
  }, [
    conversationId,
    loading,
    markShouldStickToBottom,
    sending,
    setMessages,
    settleScrollAfterPaint,
  ]);

  useEffect(() => {
    let cancelled = false;
    let timeoutHandle: ReturnType<typeof setTimeout> | null = null;

    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (cancelled) return;

        timeoutHandle = setTimeout(() => {
          if (!cancelled) {
            setShowStyleBadge(true);
          }
        }, 250);
      });
    });

    return () => {
      cancelled = true;
      if (timeoutHandle) {
        clearTimeout(timeoutHandle);
      }
    };
  }, []);

  return (
    <main className="flex-1 flex flex-col min-w-0 min-h-0 relative">
      {showStyleBadge ? (
        <LazyConversationStyleBadge
          conversationId={conversationId}
          initialStyleProfileId={initialStyleProfileId}
          initialStyleProfileName={initialStyleProfileName}
        />
      ) : null}
<div
        ref={scrollRef}
        className="flex-1 min-h-0 overflow-y-auto overscroll-contain"
      >
        <ChatMessageList
          messages={messages}
          loading={loading}
          historySettled={historySettled}
          hasMoreMessages={hasMoreMessages}
          loadingEarlier={loadingEarlier}
          onLoadEarlier={loadEarlierMessages}
        />
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
