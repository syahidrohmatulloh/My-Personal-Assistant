"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { listMessages, type Message } from "@/lib/api"

type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string }

const MESSAGE_PAGE_SIZE = 80
const LIVE_REFRESH_INTERVAL_MS = 15_000
const BOTTOM_STICKINESS_PX = 120

function messageCreatedAtMs(message: LocalMessage) {
  const value = message.created_at
  if (!value) return Number.MAX_SAFE_INTEGER

  const time = new Date(value).getTime()
  return Number.isNaN(time) ? Number.MAX_SAFE_INTEGER : time
}

function compareMessagesByCreatedAt(a: LocalMessage, b: LocalMessage) {
  const diff = messageCreatedAtMs(a) - messageCreatedAtMs(b)
  if (diff !== 0) return diff
  return String(a.id).localeCompare(String(b.id))
}


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
  liveRefreshEnabled = true,
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
  liveRefreshEnabled?: boolean
}) {
  const [hasMoreMessages, setHasMoreMessages] = useState(initialHasMoreMessages)
  const [loadingEarlier, setLoadingEarlier] = useState(false)
  const liveRefreshInFlightRef = useRef(false)

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

  useEffect(() => {
    if (!liveRefreshEnabled) return

    let cancelled = false
    let intervalHandle: ReturnType<typeof setInterval> | null = null

    const refreshLatestMessages = async () => {
      if (cancelled) return
      if (loadingEarlier) return
      if (liveRefreshInFlightRef.current) return
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return

      liveRefreshInFlightRef.current = true

      try {
        const latestMessages = await listMessages(conversationId, { limit: MESSAGE_PAGE_SIZE })
        if (cancelled || latestMessages.length === 0) return

        const container = scrollRef.current
        const shouldStick =
          !container ||
          container.scrollHeight - container.scrollTop - container.clientHeight <= BOTTOM_STICKINESS_PX

        let appendedCount = 0

        setMessages((current) => {
          const existingIds = new Set(current.map((message) => message.id))
          const newMessages = latestMessages.filter((message) => !existingIds.has(message.id))

          if (newMessages.length === 0) {
            return current
          }

          appendedCount = newMessages.length

          return [...current, ...newMessages].sort(compareMessagesByCreatedAt)
        })

        if (shouldStick && appendedCount > 0) {
          markShouldStickToBottom()
          settleScrollAfterPaint(() => !cancelled)
        }
      } catch (err) {
        console.error(err)
      } finally {
        liveRefreshInFlightRef.current = false
      }
    }

    const runSoon = () => {
      window.setTimeout(() => {
        void refreshLatestMessages()
      }, 750)
    }

    runSoon()

    const onFocus = () => {
      void refreshLatestMessages()
    }

    const onVisibilityChange = () => {
      if (document.visibilityState === "visible") {
        void refreshLatestMessages()
      }
    }

    window.addEventListener("focus", onFocus)
    document.addEventListener("visibilitychange", onVisibilityChange)

    intervalHandle = setInterval(refreshLatestMessages, LIVE_REFRESH_INTERVAL_MS)

    return () => {
      cancelled = true
      window.removeEventListener("focus", onFocus)
      document.removeEventListener("visibilitychange", onVisibilityChange)

      if (intervalHandle) {
        clearInterval(intervalHandle)
      }
    }
  }, [
    conversationId,
    liveRefreshEnabled,
    loadingEarlier,
    markShouldStickToBottom,
    scrollRef,
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
