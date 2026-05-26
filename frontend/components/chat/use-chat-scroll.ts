"use client"

import { useCallback, useEffect, useRef, useState } from "react"

const STICK_THRESHOLD = 120

function scrollContainerToBottom(el: HTMLDivElement | null, smooth = false) {
  if (!el) return

  if (smooth) {
    el.scrollTo({ top: el.scrollHeight, behavior: "auto" })
  } else {
    el.scrollTop = el.scrollHeight
  }
}

export function useChatScroll({
  messageCount,
  followSignal,
}: {
  messageCount: number
  followSignal: unknown
}) {
  const scrollRef = useRef<HTMLDivElement>(null)
  const stickToBottomRef = useRef(true)
  const [showJumpBtn, setShowJumpBtn] = useState(false)

  const markShouldStickToBottom = useCallback(() => {
    stickToBottomRef.current = true
    setShowJumpBtn(false)
  }, [])

  const jumpToBottom = useCallback(() => {
    scrollContainerToBottom(scrollRef.current, true)
    markShouldStickToBottom()
  }, [markShouldStickToBottom])

  const settleScrollAfterPaint = useCallback(
    (shouldRun: () => boolean, afterScroll?: () => void) => {
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (!shouldRun()) return

          scrollContainerToBottom(scrollRef.current)
          afterScroll?.()
        })
      })
    },
    [],
  )

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return

    function onScroll() {
      if (!el) return

      const distance = el.scrollHeight - el.scrollTop - el.clientHeight
      const nearBottom = distance < STICK_THRESHOLD

      stickToBottomRef.current = nearBottom
      setShowJumpBtn(!nearBottom && messageCount > 0)
    }

    el.addEventListener("scroll", onScroll, { passive: true })

    return () => {
      el.removeEventListener("scroll", onScroll)
    }
  }, [messageCount])

  useEffect(() => {
    if (!stickToBottomRef.current) return

    scrollContainerToBottom(scrollRef.current)
  }, [followSignal])

  return {
    scrollRef,
    stickToBottomRef,
    showJumpBtn,
    jumpToBottom,
    settleScrollAfterPaint,
    markShouldStickToBottom,
  }
}
