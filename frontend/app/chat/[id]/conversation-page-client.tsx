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
  type ChatStreamMeta,
  type Message,
} from "@/lib/api";



type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string };

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
    liveRefreshEnabled: !sending,
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
