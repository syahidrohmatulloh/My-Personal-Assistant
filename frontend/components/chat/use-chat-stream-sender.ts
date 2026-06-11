"use client"

import { useCallback, useRef } from "react"
import { useQueryClient } from "@tanstack/react-query"

import {
  streamChat,
  type ChatStreamMeta,
  type Conversation,
  type Identity,
  type Message,
} from "@/lib/api"
import { setBackgroundMoodHint } from "@/lib/ambient-background"
import {
  updateCompanionMoodFromMessage,
  shouldDeferCompanionMoodToAssistant,
  setPendingCompanionMoodSimulation,
  updateCompanionMoodFromAssistantText,
  shouldRespectCompanionMoodOverride,
} from "@/lib/companion-mood"
import { clearCalendarEventsSnapshotsForCurrentUser } from "@/lib/calendar-snapshot"

type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string }


type AssistantModeCommandTarget = "life_companion" | "chief_of_staff"

function normaliseAssistantModeCommandText(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim()
}

function detectAssistantModeCommandTarget(text: string): AssistantModeCommandTarget | null {
  const value = normaliseAssistantModeCommandText(text)
  if (!value) return null

  const questionPrefixes = [
    "apa ",
    "apa itu",
    "apakah ",
    "what ",
    "what is",
    "jelasin",
    "jelaskan",
    "explain",
    "maksud",
    "contoh",
    "bedanya",
    "how ",
    "how do",
    "how should",
    "why ",
  ]

  if (questionPrefixes.some((prefix) => value.startsWith(prefix))) {
    return null
  }

  const discussionMarkers = [
    "mau buat",
    "lagi mau buat",
    "buat 2 mode",
    "buat dua mode",
    "bikin 2 mode",
    "bikin dua mode",
    "develop 2 mode",
    "develop dua mode",
    "fitur mode",
    "feature mode",
    "desain mode",
    "design mode",
    "konsep mode",
    "rancang mode",
    "2 mode nih",
    "dua mode nih",
    "i want to build",
    "i wanna build",
    "i am building",
    "im building",
    "i m building",
    "i want to create",
    "i wanna create",
    "i am creating",
    "im creating",
    "i m creating",
    "i am designing",
    "im designing",
    "i m designing",
    "lets design",
    "let us design",
    "lets improve",
    "let us improve",
    "change the prompt",
    "changing the prompt",
    "improve the prompt",
    "prompt for",
    "compare",
    "comparison",
    "two modes",
    "2 modes",
    "build two modes",
    "create two modes",
    "design two modes",
    "mode feature",
    "feature for",
    "prototype",
    "sandbox",
  ]

  const mentionsChief =
    value.includes("chief") || value.includes("serius") || value.includes("executive")
  const mentionsCompanion =
    value.includes("companion") || value.includes("santai") || value.includes("hangat")
  const mentionsMode = value.includes("mode") || value.includes("modes")

  if (mentionsMode && discussionMarkers.some((marker) => value.includes(marker))) {
    return null
  }

  if (
    mentionsChief &&
    mentionsCompanion &&
    discussionMarkers.some((marker) => value.includes(marker))
  ) {
    return null
  }

  const chiefPatterns = [
    "mode serius",
    "serius dulu",
    "serius lagi",
    "mode kerja",
    "mode eksekusi",
    "mode executive",
    "mode eksekutif",
    "mode chief dulu",
    "mode chief lagi",
    "chief mode dulu",
    "chief mode lagi",
    "mode chief of staff dulu",
    "mode chief of staff lagi",
    "chief of staff dulu",
    "chief of staff lagi",
    "chief of staff mode dulu",
    "chief of staff mode lagi",
    "jadi chief of staff",
    "masuk chief of staff",
    "aktifkan chief of staff",
    "switch to chief of staff",
    "switch me to chief of staff",
    "change to chief of staff",
    "change me to chief of staff",
    "turn on chief of staff",
    "use chief of staff",
    "use chief of staff mode",
    "be my chief of staff",
    "pakai chief of staff",
    "sebagai chief of staff",
  ]

  const lifePatterns = [
    "balik companion",
    "balik companion mode",
    "balik life companion",
    "balik life companion mode",
    "kembali companion",
    "kembali companion mode",
    "kembali life companion",
    "kembali life companion mode",
    "mode companion dulu",
    "mode companion lagi",
    "companion mode dulu",
    "companion mode lagi",
    "companion dulu",
    "companion lagi",
    "life companion dulu",
    "life companion lagi",
    "life companion mode dulu",
    "life companion mode lagi",
    "mode santai",
    "mode personal",
    "mode teman",
    "mode hangat",
    "mode ngobrol",
    "mode biasa",
    "switch to life companion",
    "switch me to life companion",
    "change to life companion",
    "change me to life companion",
    "turn on life companion",
    "use life companion",
    "use life companion mode",
  ]

  const padded = ` ${value} `
  const chief = chiefPatterns.find((pattern) => padded.includes(` ${pattern} `))
  const life = lifePatterns.find((pattern) => padded.includes(` ${pattern} `))

  if (chief && life) {
    return value.lastIndexOf(chief) > value.lastIndexOf(life)
      ? "chief_of_staff"
      : "life_companion"
  }

  if (chief) return "chief_of_staff"
  if (life) return "life_companion"
  return null
}

function dispatchAssistantModeForInstantBackground(mode: AssistantModeCommandTarget) {
  window.dispatchEvent(
    new CustomEvent("assistant-companion-settings", {
      detail: { assistant_mode: mode },
    }),
  )
}


function shouldInvalidateCalendarSnapshotAfterChat(userText: string, assistantText: string): boolean {
  const combined = `${userText}\n${assistantText}`.toLowerCase()

  const calendarSignals = [
    "calendar",
    "kalender",
    "google calendar",
    "google kalender",
    "jadwal",
    "agenda",
    "acara",
    "event",
    "meeting",
    "rapat",
    "pukul",
    "jam ",
    "besok",
    "lusa",
    "nanti",
    "hari ini",
    "minggu depan",
    "bulan depan",
    "masukin",
    "masukkan",
    "tambahkan",
    "tambahin",
    "catat",
    "hapus",
    "delete",
    "reschedule",
    "jadwal ulang",
    "geser",
    "pindahin",
    "ubah",
    "edit",
  ]

  return calendarSignals.some((signal) => combined.includes(signal))
}

function applyAssistantMoodAfterLatestMessagePaint(
  assistantText: string,
  conversationId: string,
) {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      window.setTimeout(() => {
        updateCompanionMoodFromAssistantText(assistantText, conversationId)
      }, 350)
    })
  })
}

export function useChatStreamSender({
  conversationId,
  input,
  setInput,
  sending,
  setSending,
  messagesLength,
  setMessages,
  setStreamMeta,
  markShouldStickToBottom,
}: {
  conversationId: string
  input: string
  setInput: React.Dispatch<React.SetStateAction<string>>
  sending: boolean
  setSending: React.Dispatch<React.SetStateAction<boolean>>
  messagesLength: number
  setMessages: React.Dispatch<React.SetStateAction<LocalMessage[]>>
  setStreamMeta: React.Dispatch<React.SetStateAction<ChatStreamMeta | null>>
  markShouldStickToBottom: () => void
}) {
  const qc = useQueryClient()
  const calendarSnapshotDirtyRef = useRef(false)

  return useCallback(
    async (attachmentIds: string[] = [], overrideText?: string) => {
      const text = (overrideText ?? input).trim()

      if (shouldDeferCompanionMoodToAssistant(text)) {
        setPendingCompanionMoodSimulation(text, conversationId)
      } else {
        updateCompanionMoodFromMessage(text, conversationId)
      }

      const hasContent = text.length > 0 || attachmentIds.length > 0
      if (!hasContent || sending) return

      const messageText = text || (attachmentIds.length > 0 ? "(shared an attachment)" : "")

      const requestedAssistantMode = detectAssistantModeCommandTarget(messageText)
      if (requestedAssistantMode) {
        dispatchAssistantModeForInstantBackground(requestedAssistantMode)
      }

      setInput("")
      setSending(true)
      setStreamMeta(null)
      calendarSnapshotDirtyRef.current = false
      markShouldStickToBottom()

      const wasFirstMessage = messagesLength === 0

      const userMsg: LocalMessage = {
        id: `local-user-${Date.now()}`,
        role: "user",
        content: messageText,
        created_at: new Date().toISOString(),
      }

      const assistantId = `local-asst-${Date.now()}`

      setMessages((prev) => [
        ...prev,
        userMsg,
        { id: assistantId, role: "assistant", content: "", pending: true },
      ])

      if (wasFirstMessage) {
        const title = messageText.slice(0, 40) + (messageText.length > 40 ? "…" : "")
        qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
          old.map((conversation) =>
            conversation.id === conversationId ? { ...conversation, title } : conversation,
          ),
        )
      }

      let assistantText = ""
      let pending = ""
      let rafId: number | null = null
      const minThinkingMs = 650
      const thinkingStartedAt = Date.now()

      const flush = () => {
        if (!pending) {
          rafId = null
          return
        }

        assistantText += pending
        pending = ""
        const snapshot = assistantText

        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? {
                  id: assistantId,
                  role: "assistant",
                  content: snapshot,
                  pending: true,
                }
              : message,
          ),
        )

        rafId = null
      }

      try {
        for await (const event of streamChat(conversationId, messageText, attachmentIds)) {
          if (event.type === "meta") {
            setStreamMeta(event)

            if (
              event.assistant_mode === "chief_of_staff" ||
              event.assistant_mode === "life_companion"
            ) {
              dispatchAssistantModeForInstantBackground(event.assistant_mode)
            }

            if (event.calendar_snapshot_dirty) {
              calendarSnapshotDirtyRef.current = true
            }

            if (event.assistant_name) {
              qc.setQueryData<Identity | undefined>(["identity"], (old) => ({
                profile: {
                  ...(old?.profile ?? {}),
                  assistant_name: event.assistant_name,
                },
                narrative: old?.narrative ?? null,
                updated_at: old?.updated_at ?? null,
              }))
            }

            if (
              (event.mood || event.background_palette_hint) &&
              !shouldRespectCompanionMoodOverride(event.mood)
            ) {
              setBackgroundMoodHint({
                mood: event.mood,
                palette: event.background_palette_hint as any,
              })
            }

            continue
          }

          if (event.type === "done") continue

          pending += event.text

          if (Date.now() - thinkingStartedAt < minThinkingMs) {
            continue
          }

          if (rafId == null) {
            rafId = requestAnimationFrame(flush)
          }
        }

        const remainingThinkingMs = minThinkingMs - (Date.now() - thinkingStartedAt)
        if (remainingThinkingMs > 0) {
          await new Promise((resolve) => window.setTimeout(resolve, remainingThinkingMs))
        }

        if (rafId != null) cancelAnimationFrame(rafId)
        flush()

        if (assistantText.trim().length === 0) {
          setMessages((prev) => prev.filter((message) => message.id !== assistantId))
        } else {
          setMessages((prev) =>
            prev.map((message) =>
              message.id === assistantId
                ? {
                    id: assistantId,
                    role: "assistant",
                    content: assistantText,
                    created_at: new Date().toISOString(),
                  }
                : message,
            ),
          )
        }

        applyAssistantMoodAfterLatestMessagePaint(assistantText, conversationId)

        if (
          calendarSnapshotDirtyRef.current ||
          shouldInvalidateCalendarSnapshotAfterChat(messageText, assistantText)
        ) {
          calendarSnapshotDirtyRef.current = false
          void clearCalendarEventsSnapshotsForCurrentUser()
        }

        setTimeout(() => {
          qc.invalidateQueries({ queryKey: ["conversations"] })
        }, 4000)
      } catch (err) {
        console.error(err)

        setMessages((prev) =>
          prev.map((message) =>
            message.id === assistantId
              ? {
                  id: assistantId,
                  role: "assistant",
                  content: `**Error:** ${err instanceof Error ? err.message : "unknown"}`,
                  created_at: new Date().toISOString(),
                }
              : message,
          ),
        )
      } finally {
        setSending(false)
        setStreamMeta(null)
      }
    },
    [
      conversationId,
      input,
      markShouldStickToBottom,
      messagesLength,
      qc,
      sending,
      setInput,
      setMessages,
      setSending,
      setStreamMeta,
    ],
  )
}
