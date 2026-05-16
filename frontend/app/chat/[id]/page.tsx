"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowDown } from "lucide-react";

import { Composer } from "@/components/chat/composer";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Skeleton } from "@/components/ui/skeleton";

import { listMessages, streamChat } from "@/lib/api";

type LocalMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at?: string;
  pending?: boolean;
};

const STICK_THRESHOLD = 120;

function scrollToBottom(el: HTMLDivElement | null) {
  if (!el) return;
  el.scrollTop = el.scrollHeight;
}

export default function ConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id: conversationId } = use(params);

  const qc = useQueryClient();

  const [messages, setMessages] = useState<LocalMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showJumpBtn, setShowJumpBtn] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const stickRef = useRef(true);

  // =========================================
  // LOAD HISTORY
  // =========================================
  useEffect(() => {
    let cancelled = false;

    async function loadMessages() {
      try {
        setLoading(true);

        const history = (await listMessages(
          conversationId,
        )) as LocalMessage[];

        if (cancelled) return;

        setMessages((prev) => {
          // jangan overwrite kalau sedang streaming
          const hasPending = prev.some((m) => m.pending);

          if (hasPending) {
            return prev;
          }

          return history;
        });

        requestAnimationFrame(() => {
          scrollToBottom(scrollRef.current);
        });
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }

    loadMessages();

    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  // =========================================
  // SCROLL DETECTOR
  // =========================================
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;

    const onScroll = () => {
      const distance =
        el.scrollHeight - el.scrollTop - el.clientHeight;

      const nearBottom = distance < STICK_THRESHOLD;

      stickRef.current = nearBottom;
      setShowJumpBtn(!nearBottom);
    };

    el.addEventListener("scroll", onScroll);

    return () => {
      el.removeEventListener("scroll", onScroll);
    };
  }, []);

  // =========================================
  // AUTO SCROLL
  // =========================================
  useEffect(() => {
    if (stickRef.current) {
      scrollToBottom(scrollRef.current);
    }
  }, [messages]);

  const jumpToBottom = () => {
    scrollToBottom(scrollRef.current);
  };

  // =========================================
  // SEND MESSAGE
  // =========================================
  const handleSend = useCallback(async () => {
    const text = input.trim();

    if (!text || sending) return;

    setInput("");
    setSending(true);

    const userId = crypto.randomUUID();
    const assistantId = crypto.randomUUID();

    // =========================================
    // OPTIMISTIC UI
    // =========================================
    setMessages((prev) => [
      ...prev,
      {
        id: userId,
        role: "user",
        content: text,
        pending: true,
        created_at: new Date().toISOString(),
      },
      {
        id: assistantId,
        role: "assistant",
        content: "",
        pending: true,
        created_at: new Date().toISOString(),
      },
    ]);

    let assistantText = "";

    try {
      for await (const chunk of streamChat(conversationId, text)) {
        assistantText += chunk;

        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content: assistantText,
                }
              : m,
          ),
        );
      }

      // =========================================
      // FINAL RECONCILE
      // =========================================
      const latest = (await listMessages(
        conversationId,
      )) as LocalMessage[];

      setMessages(latest);

      // sidebar refresh
      qc.invalidateQueries({
        queryKey: ["conversations"],
      });
    } catch (err) {
      console.error(err);

      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                content: "Error terjadi",
                pending: false,
              }
            : m,
        ),
      );
    } finally {
      setSending(false);
    }
  }, [conversationId, input, sending, qc]);

  // =========================================
  // UI
  // =========================================
  return (
    <main className="flex flex-col h-full relative">
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-4 space-y-3"
      >
        {loading ? (
          <>
            <Skeleton className="h-10 w-3/4" />
            <Skeleton className="h-20 w-4/5" />
          </>
        ) : messages.length === 0 ? (
          <p className="text-center text-sm text-gray-500">
            Say hello — I’m listening.
          </p>
        ) : (
          messages.map((m) => (
            <MessageBubble
              key={m.id}
              role={m.role}
              content={m.content}
              pending={m.pending}
            />
          ))
        )}
      </div>

      {showJumpBtn && (
        <button
          onClick={jumpToBottom}
          className="absolute bottom-24 left-1/2 -translate-x-1/2 bg-black text-white px-3 py-1 rounded-full text-xs flex items-center gap-1"
        >
          <ArrowDown size={14} />
          Jump
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