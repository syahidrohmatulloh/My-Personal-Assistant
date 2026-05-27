"use client"

import { memo } from "react"

import { MessageBubble } from "@/components/chat/message-bubble"
import { Skeleton } from "@/components/ui/skeleton"
import type { Message } from "@/lib/api"

type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string }

type ChatMessageRowProps = {
  message: LocalMessage
}

const ChatMessageRow = memo(
  function ChatMessageRow({ message }: ChatMessageRowProps) {
    return (
      <MessageBubble
        role={message.role}
        content={message.content}
        pending={"pending" in message && message.pending === true}
      />
    )
  },
  (prev, next) =>
    prev.message.id === next.message.id &&
    prev.message.role === next.message.role &&
    prev.message.content === next.message.content &&
    ("pending" in prev.message ? prev.message.pending : false) ===
      ("pending" in next.message ? next.message.pending : false),
)

export const ChatMessageList = memo(function ChatMessageList({
  messages,
  loading,
  historySettled,
}: {
  messages: LocalMessage[]
  loading: boolean
  historySettled: boolean
}) {
  return (
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
        messages.map((message) => <ChatMessageRow key={message.id} message={message} />)
      )}
    </div>
  )
})
