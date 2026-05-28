"use client"

import { useCallback, useEffect, useState } from "react"
import { listMessages, type Message } from "@/lib/api"

type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string }

const MESSAGE_PAGE_SIZE = 80

export function useChatMessageLoader({
  conversationId,
  initialMessages = [],
  initialHasMoreMessages = false,
  scrollRef,
  setMessages,
  setLoading,
  setHistorySettled,
  markShouldStickToBottom,
  settleScrollAfterPaint,
}: {
  conversationId: string
  initialMessages?: Message[]
  initialHasMoreMessages?: boolean
  scrollRef: React.RefObject<HTMLDivElement | null>
  setMessages: React.Dispatch<React.SetStateAction<LocalMessage[]>>
  setLoading: React.Dispatch<React.SetStateAction<boolean>>
  setHistorySettled: React.Dispatch<React.SetStateAction<boolean>>
  markShouldStickToBottom: () => void
  settleScrollAfterPaint: (shouldRun: () => boolean, afterScroll?: () => void) => void
}) {
  const [hasMoreMessages, setHasMoreMessages] = useState(initialHasMoreMessages)
  const [loadingEarlier, setLoadingEarlier] = useState(false)

  useEffect(() => {
    let cancelled = false

    setLoading(initialMessages.length === 0)
    setHistorySettled(false)
    setHasMoreMessages(initialHasMoreMessages)
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

    listMessages(conversationId, { limit: MESSAGE_PAGE_SIZE })
      .then((loadedMessages) => {
        if (cancelled) return

        setMessages(loadedMessages)
        setHasMoreMessages(loadedMessages.length >= MESSAGE_PAGE_SIZE)
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
    initialHasMoreMessages,
    initialMessages,
    markShouldStickToBottom,
    setHistorySettled,
    setLoading,
    setMessages,
    settleScrollAfterPaint,
  ])

  const loadEarlierMessages = useCallback(async () => {
    if (loadingEarlier || !hasMoreMessages) return

    let before: string | null = null

    setMessages((current) => {
      const firstPersisted = current.find(
        (message) => !("pending" in message) && typeof message.created_at === "string",
      )
      before = firstPersisted?.created_at ?? null
      return current
    })

    if (!before) {
      setHasMoreMessages(false)
      return
    }

    const container = scrollRef.current
    const previousScrollHeight = container?.scrollHeight ?? 0
    const previousScrollTop = container?.scrollTop ?? 0

    setLoadingEarlier(true)

    try {
      const olderMessages = await listMessages(conversationId, {
        limit: MESSAGE_PAGE_SIZE,
        before,
      })

      setHasMoreMessages(olderMessages.length >= MESSAGE_PAGE_SIZE)

      if (olderMessages.length > 0) {
        setMessages((current) => {
          const existingIds = new Set(current.map((message) => message.id))
          const dedupedOlder = olderMessages.filter((message) => !existingIds.has(message.id))
          return [...dedupedOlder, ...current]
        })

        requestAnimationFrame(() => {
          const nextContainer = scrollRef.current
          if (!nextContainer) return

          const nextScrollHeight = nextContainer.scrollHeight
          nextContainer.scrollTop =
            previousScrollTop + (nextScrollHeight - previousScrollHeight)
        })
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoadingEarlier(false)
    }
  }, [
    conversationId,
    hasMoreMessages,
    loadingEarlier,
    scrollRef,
    setMessages,
  ])

  return {
    hasMoreMessages,
    loadingEarlier,
    loadEarlierMessages,
  }
}
