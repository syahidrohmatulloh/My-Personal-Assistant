"use client"

import { useEffect } from "react"

import type { Identity } from "@/lib/api"
import {
  coerceBackgroundSettings,
  readBackgroundSettings,
  saveBackgroundSettings,
} from "@/lib/ambient-background"
import { hydrateCompanionMoodForConversation } from "@/lib/companion-mood"
import { subscribeCompanionMoodRealtime } from "@/lib/companion-mood-realtime"

type IdleWindow = Window & {
  requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number
  cancelIdleCallback?: (handle: number) => void
}

function scheduleAfterChatIdle(callback: () => void, delayMs = 1500): () => void {
  if (typeof window === "undefined") {
    return () => {}
  }

  let cancelled = false
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null
  let idleHandle: number | null = null

  timeoutHandle = setTimeout(() => {
    if (cancelled) return

    const idleWindow = window as IdleWindow
    if (idleWindow.requestIdleCallback) {
      idleHandle = idleWindow.requestIdleCallback(
        () => {
          if (!cancelled) callback()
        },
        { timeout: 3500 },
      )
    } else {
      callback()
    }
  }, delayMs)

  return () => {
    cancelled = true

    if (timeoutHandle) {
      clearTimeout(timeoutHandle)
    }

    const idleWindow = window as IdleWindow
    if (idleHandle != null && idleWindow.cancelIdleCallback) {
      idleWindow.cancelIdleCallback(idleHandle)
    }
  }
}

export function useChatRuntimeEffects({
  conversationId,
  identity,
}: {
  conversationId: string
  identity?: Identity
}) {
  useEffect(() => {
    let unsubscribe: (() => void) | null = null
    let cancelled = false

    const cancelIdle = scheduleAfterChatIdle(() => {
      if (cancelled) return

      void hydrateCompanionMoodForConversation(conversationId)

      subscribeCompanionMoodRealtime(conversationId).then((fn) => {
        if (cancelled) {
          fn()
          return
        }

        unsubscribe = fn
      })
    })

    return () => {
      cancelled = true
      cancelIdle()
      if (unsubscribe) unsubscribe()
    }
  }, [conversationId])

  useEffect(() => {
    const savedSettings = identity?.profile?.background_settings

    if (!savedSettings) return

    const mergedSettings = coerceBackgroundSettings(
      savedSettings,
      readBackgroundSettings(),
    )

    saveBackgroundSettings(mergedSettings)

    window.dispatchEvent(
      new CustomEvent("assistant.background.settings.changed", {
        detail: { reason: "identity-background-sync" },
      }),
    )
  }, [identity])

  useEffect(() => {
    if (typeof window === "undefined") return

    window.localStorage.setItem(
      "assistant.lastChatPath",
      window.location.pathname,
    )
  }, [conversationId])
}
