"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Composer } from "@/components/chat/composer";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Skeleton } from "@/components/ui/skeleton";
import { listMessages, streamChat, type Conversation, type Message } from "@/lib/api";

type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string };

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
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listMessages(conversationId)
      .then((msgs) => !cancelled && setMessages(msgs))
      .catch(console.error)
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [conversationId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    setInput("");
    setSending(true);

    const wasFirstMessage = messages.length === 0;

    const userMsg: LocalMessage = {
      id: `local-user-${Date.now()}`,
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
    };
    const assistantId = `local-asst-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      userMsg,
      { id: assistantId, role: "assistant", content: "", pending: true },
    ]);

    // Optimistic title from first 40 chars of user message
    if (wasFirstMessage) {
      const title = text.slice(0, 40) + (text.length > 40 ? "…" : "");
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.map((c) => (c.id === conversationId ? { ...c, title } : c)),
      );
    }

    // ---------- Streaming with rAF batching ----------
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
      for await (const delta of streamChat(conversationId, text)) {
        pending += delta;
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

      // Invalidate so server-side title (Haiku) eventually overrides optimistic
      qc.invalidateQueries({ queryKey: ["conversations"] });
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
    }
  }, [conversationId, input, messages.length, qc, sending]);

  return (
    <main className="flex-1 flex flex-col min-w-0">
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 py-6 space-y-4">
          {loading ? (
            <>
              <Skeleton className="h-12 w-3/4 ml-auto" />
              <Skeleton className="h-20 w-4/5" />
              <Skeleton className="h-10 w-2/3 ml-auto" />
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
          <div ref={bottomRef} />
        </div>
      </div>
      <Composer
        value={input}
        onChange={setInput}
        onSubmit={handleSend}
        disabled={sending}
      />
    </main>
  );
}
