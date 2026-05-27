"use client"

import { useEffect } from "react"
import { listMessages, type Message } from "@/lib/api"

type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string }

export function useChatMessageLoader({
  conversationId,
  initialMessages = [],
  setMessages,
  setLoading,
  setHistorySettled,
  markShouldStickToBottom,
  settleScrollAfterPaint,
}: {
  conversationId: string
  initialMessages?: Message[]
  setMessages: React.Dispatch<React.SetStateAction<LocalMessage[]>>
  setLoading: React.Dispatch<React.SetStateAction<boolean>>
  setHistorySettled: React.Dispatch<React.SetStateAction<boolean>>
  markShouldStickToBottom: () => void
  settleScrollAfterPaint: (shouldRun: () => boolean, afterScroll?: () => void) => void
}) {
  useEffect(() => {
    let cancelled = false

    setLoading(initialMessages.length === 0)
    setHistorySettled(false)
    markShouldStickToBottom()

    const settleAfterPaint = () => {
      settleScrollAfterPaint(
        () => !cancelled,
        () => setHistorySettled(true),
      )
    }

    if (initialMessages.length > 0) {
      setMessages(initialMessages)
      setLoading(false)
      settleAfterPaint()

      return () => {
        cancelled = true
      }
    }

    listMessages(conversationId)
      .then((loadedMessages) => {
        if (cancelled) return

        setMessages(loadedMessages)
        setLoading(false)
        settleAfterPaint()
      })
      .catch((err) => {
        console.error(err)

        if (!cancelled) {
          setLoading(false)
          setHistorySettled(true)
        }
      })

    return () => {
      cancelled = true
    }
  }, [
    conversationId,
    initialMessages,
    markShouldStickToBottom,
    setHistorySettled,
    setLoading,
    setMessages,
    settleScrollAfterPaint,
  ])
}
