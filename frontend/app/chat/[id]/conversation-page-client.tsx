"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";

import { Composer } from "@/components/chat/composer";
import { MessageBubble } from "@/components/chat/message-bubble";
import { ConversationStyleBadge } from "@/components/chat/conversation-style-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useChatScroll } from "@/components/chat/use-chat-scroll";
import { useChatMessageLoader } from "@/components/chat/use-chat-message-loader";
import { useChatStreamSender } from "@/components/chat/use-chat-stream-sender";
import { useChatRuntimeEffects } from "@/components/chat/use-chat-runtime-effects";
import { useChatPrefill } from "@/components/chat/use-chat-prefill";

import {
  getIdentity,
  getMainConversation,
  type ChatStreamMeta,
  type Message,
} from "@/lib/api";



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
