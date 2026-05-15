"use client";

import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { cn } from "@/lib/utils";

type Props = {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
};

function MessageBubbleBase({ role, content, pending }: Props) {
  const isUser = role === "user";

  return (
    <div className={cn("flex w-full fade-up", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[88%] sm:max-w-[78%] rounded-2xl px-4 py-3 text-[15px] leading-relaxed",
          isUser
            ? "bg-accent text-on-accent shadow-lg shadow-accent/20"
            : "glass text-fg",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{content}</p>
        ) : (
          <div className="prose-chat break-words">
            {content ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {content}
              </ReactMarkdown>
            ) : pending ? (
              <PendingDots />
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

export const MessageBubble = memo(
  MessageBubbleBase,
  (a, b) =>
    a.role === b.role && a.content === b.content && a.pending === b.pending,
);

function PendingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      <span className="h-2 w-2 rounded-full bg-accent pulse-dot" style={{ animationDelay: "0ms" }} />
      <span className="h-2 w-2 rounded-full bg-accent pulse-dot" style={{ animationDelay: "200ms" }} />
      <span className="h-2 w-2 rounded-full bg-accent pulse-dot" style={{ animationDelay: "400ms" }} />
    </div>
  );
}
