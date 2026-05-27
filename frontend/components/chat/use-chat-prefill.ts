"use client"

import { useEffect, useRef } from "react"
import { useRouter, useSearchParams } from "next/navigation"

export function useChatPrefill({
  conversationId,
  input,
  setInput,
  loading,
  sending,
  messagesLength,
  handleSend,
}: {
  conversationId: string
  input: string
  setInput: React.Dispatch<React.SetStateAction<string>>
  loading: boolean
  sending: boolean
  messagesLength: number
  handleSend: (attachmentIds?: string[], overrideText?: string) => Promise<void>
}) {
  const router = useRouter()
  const searchParams = useSearchParams()
  const consumedPrefillRef = useRef<string | null>(null)

  // Calendar handoff: fill the composer with a scheduling-help draft from /calendar.
  useEffect(() => {
    if (typeof window === "undefined") return
    if (loading || sending) return
    if (input.trim().length > 0) return

    const key = "app:calendar-chat-handoff-draft"
    const draft = window.localStorage.getItem(key)?.trim()

    if (!draft) return

    window.localStorage.removeItem(key)
    setInput(draft)
  }, [input, loading, sending, setInput])

  // Auto-send a landing-page prefill once when a new conversation is opened.
  useEffect(() => {
    const prefill = searchParams.get("prefill")?.trim()

    if (!prefill) return
    if (loading || sending) return
    if (consumedPrefillRef.current === prefill) return
    if (messagesLength > 0) return

    consumedPrefillRef.current = prefill
    setInput(prefill)

    void handleSend([], prefill)

    const nextParams = new URLSearchParams(searchParams.toString())
    nextParams.delete("prefill")
    const qs = nextParams.toString()

    router.replace(qs ? `/chat/${conversationId}?${qs}` : `/chat/${conversationId}`, {
      scroll: false,
    })
  }, [
    conversationId,
    handleSend,
    loading,
    messagesLength,
    router,
    searchParams,
    sending,
    setInput,
  ])
}
