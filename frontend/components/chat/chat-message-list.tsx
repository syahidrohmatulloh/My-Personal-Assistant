"use client"

import { Fragment, memo } from "react"

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

function localDateKey(value?: string | null) {
  if (!value) return null

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return null

  return [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
  ].join("-")
}

function isIndonesianLocale() {
  if (typeof navigator === "undefined") return false
  return navigator.language.toLowerCase().startsWith("id")
}

function startOfLocalDay(date: Date) {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate())
}

function formatMessageTime(value?: string | null) {
  const date = value ? new Date(value) : new Date()

  if (Number.isNaN(date.getTime())) {
    return ""
  }

  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

function formatDateSeparator(value?: string | null) {
  if (!value) return ""

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ""

  const today = startOfLocalDay(new Date())
  const target = startOfLocalDay(date)
  const diffDays = Math.round((today.getTime() - target.getTime()) / 86_400_000)
  const useIndonesian = isIndonesianLocale()

  if (diffDays === 0) return useIndonesian ? "Hari ini" : "Today"
  if (diffDays === 1) return useIndonesian ? "Kemarin" : "Yesterday"

  return new Intl.DateTimeFormat(undefined, {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: today.getFullYear() === target.getFullYear() ? undefined : "numeric",
  }).format(date)
}

function shouldShowDateSeparator(
  previous?: LocalMessage | null,
  current?: LocalMessage | null,
) {
  if (!current?.created_at) return false
  if (!previous?.created_at) return true

  return localDateKey(previous.created_at) !== localDateKey(current.created_at)
}

function ChatDateSeparator({ value }: { value?: string | null }) {
  const label = formatDateSeparator(value)
  if (!label) return null

  return (
    <div className="flex justify-center py-3">
      <span className="rounded-full border border-border bg-bg/80 px-3 py-1 text-[11px] font-medium text-fg-muted shadow-sm backdrop-blur-md">
        {label}
      </span>
    </div>
  )
}

function ChatMessageWithTimestamp({ message }: { message: LocalMessage }) {
  const isUser = message.role === "user"
  const time = formatMessageTime(message.created_at)

  return (
    <div>
      <ChatMessageRow message={message} />
      {time ? (
        <div
          className={[
            "-mt-1 px-4 text-[10px] leading-none text-fg-subtle",
            isUser ? "text-right" : "text-left",
          ].join(" ")}
        >
          {time}
        </div>
      ) : null}
    </div>
  )
}

export const ChatMessageList = memo(function ChatMessageList({
  messages,
  loading,
  historySettled,
  hasMoreMessages = false,
  loadingEarlier = false,
  onLoadEarlier,
}: {
  messages: LocalMessage[]
  loading: boolean
  historySettled: boolean
  hasMoreMessages?: boolean
  loadingEarlier?: boolean
  onLoadEarlier?: () => void
}) {
  return (
    <div
      className={[
        "max-w-3xl mx-auto px-3 sm:px-6 py-4 sm:py-6 space-y-3 sm:space-y-4",
        !loading && messages.length > 0 && !historySettled ? "opacity-0" : "opacity-100",
      ].join(" ")}
    >
      {!loading && hasMoreMessages ? (
        <div className="flex justify-center pb-2">
          <button
            type="button"
            onClick={onLoadEarlier}
            disabled={loadingEarlier}
            className="rounded-full border border-slate-200 bg-white/80 px-4 py-2 text-xs font-medium text-slate-600 shadow-sm transition hover:bg-white disabled:cursor-wait disabled:opacity-60 dark:border-white/10 dark:bg-white/[0.06] dark:text-zinc-300 dark:hover:bg-white/[0.1]"
          >
            {loadingEarlier ? "Loading earlier..." : "Load earlier messages"}
          </button>
        </div>
      ) : null}

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
        messages.map((message, index) => (
          <Fragment key={message.id}>
            {shouldShowDateSeparator(messages[index - 1], message) ? (
              <ChatDateSeparator value={message.created_at} />
            ) : null}
            <ChatMessageWithTimestamp message={message} />
          </Fragment>
        ))
      )}
    </div>
  )
})
