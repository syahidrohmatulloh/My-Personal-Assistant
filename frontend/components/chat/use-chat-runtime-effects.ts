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

    void hydrateCompanionMoodForConversation(conversationId)

    subscribeCompanionMoodRealtime(conversationId).then((fn) => {
      if (cancelled) {
        fn()
        return
      }

      unsubscribe = fn
    })

    return () => {
      cancelled = true
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
