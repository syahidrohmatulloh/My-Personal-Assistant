"use client"

import { useEffect } from "react"
import {
  type Goal,
  type GoalActionProposal,
  type GoalSuggestion,
  type Person,
  listGoalActionProposals,
  listGoalSuggestions,
  listGoals,
  listPeople,
} from "@/lib/api"
import { userScopedSnapshotKey, writeSnapshot } from "@/lib/snapshot-cache"

type MemoryReviewPayload = {
  active: Record<string, unknown[]>
  archived: Record<string, unknown[]>
  counts: {
    active: number
    archived: number
    total: number
  }
}

type MemoryQualityPayload = {
  summary: {
    active_memories: number
    duplicate_groups: number
    conflict_groups: number
    low_quality_memories: number
    stale_memories?: number
    needs_review: number
  }
  review_items: unknown[]
}

type MemoryHealthSchedulerStatus = {
  enabled?: boolean
  running?: boolean
  interval_minutes?: number
  last_started_at?: string | null
  last_finished_at?: string | null
  last_error?: string | null
  health_source?: "scheduler" | "live" | "none"
  user_summary?: {
    needs_review?: number
    duplicate_groups?: number
    conflict_groups?: number
    low_quality_memories?: number
    stale_memories?: number
  } | null
}

type MemoriesSnapshotData = {
  data: MemoryReviewPayload | null
  quality: MemoryQualityPayload | null
  memoryHealthStatus: MemoryHealthSchedulerStatus | null
}

type RawCalendarItem = {
  id?: string
  title?: string
  content?: string
  structured_value?: string
  due_date?: string
  calendar_event_status?: string | null
  calendar_event_title?: string | null
  calendar_event_date?: string | null
  calendar_event_start_at?: string | null
  calendar_event_end_at?: string | null
  calendar_event_all_day?: boolean | null
  google_calendar_event_link?: string | null
  calendar_sync_error?: string | null
}

type CalendarEvent = {
  id: string
  title: string
  date: string
  startAt: string | null
  endAt: string | null
  allDay: boolean
  status: "confirmed_local" | "synced_google"
  googleLink: string | null
  syncError: string | null
}

type GoalsSnapshotData = {
  filter: Goal["status"] | "all"
  goals: Goal[]
  suggestions: GoalSuggestion[]
  actionProposals: GoalActionProposal[]
}

type IdleWindow = Window & {
  requestIdleCallback?: (callback: () => void, options?: { timeout?: number }) => number
  cancelIdleCallback?: (handle: number) => void
}

function normalizeCalendarTitle(item: RawCalendarItem): string {
  const raw =
    item.calendar_event_title ||
    item.title ||
    item.structured_value ||
    item.content ||
    "Untitled event"

  const cleaned = String(raw)
    .replace(/\s*\|\s*due_date=.*$/i, "")
    .replace(/^User has a scheduled event:\s*/i, "")
    .replace(/\s+on\s+\d{4}-\d{2}-\d{2}.*$/i, "")
    .replace(/^(beb|sayang|yang|aku|saya|gue|gw|gua)\s+/i, "")
    .replace(/^(sekarang|nanti|besok|lusa|hari ini|pagi ini|siang ini|sore ini|malam ini)\s+/i, "")
    .replace(/^(ini\s+)?(mau|akan|bakal|hendak)\s+/i, "")
    .replace(/^(ada\s+)?(acara|agenda|jadwal)\s+/i, "")
    .replace(/^ke\s+/i, "")
    .replace(/\s+(ya|yah|dong|deh|nih|sih|ah|hehe|beb)$/i, "")
    .replace(/\s+/g, " ")
    .trim()

  return cleaned ? cleaned.charAt(0).toUpperCase() + cleaned.slice(1) : "Calendar event"
}

function normalizeCalendarEvent(item: RawCalendarItem): CalendarEvent | null {
  const status = item.calendar_event_status

  if (status !== "confirmed_local" && status !== "synced_google") {
    return null
  }

  const id = String(item.id || "").trim()
  const date = String(item.calendar_event_date || item.due_date || "").trim()

  if (!id || !date) {
    return null
  }

  return {
    id,
    title: normalizeCalendarTitle(item),
    date,
    startAt: item.calendar_event_start_at || null,
    endAt: item.calendar_event_end_at || null,
    allDay: Boolean(item.calendar_event_all_day),
    status,
    googleLink: item.google_calendar_event_link || null,
    syncError: item.calendar_sync_error || null,
  }
}

function calendarSortKey(event: CalendarEvent): string {
  return `${event.date} ${event.startAt || "99:99"} ${event.title}`
}

function scopedKey(userId: string, area: string): string {
  return userScopedSnapshotKey({ userId, area })
}

async function prewarmPeople(userId: string) {
  const people = await listPeople()
  writeSnapshot<Person[]>(scopedKey(userId, "people"), people)
}

async function prewarmGoals(userId: string) {
  const [goalsResult, suggestionsResult, actionsResult] = await Promise.allSettled([
    listGoals("active"),
    listGoalSuggestions("pending"),
    listGoalActionProposals("pending"),
  ])

  const payload: GoalsSnapshotData = {
    filter: "active",
    goals: goalsResult.status === "fulfilled" ? goalsResult.value : [],
    suggestions: suggestionsResult.status === "fulfilled" ? suggestionsResult.value : [],
    actionProposals: actionsResult.status === "fulfilled" ? actionsResult.value : [],
  }

  writeSnapshot<GoalsSnapshotData>(`${scopedKey(userId, "goals")}:active`, payload)
}

async function prewarmCalendar(userId: string) {
  const response = await fetch("/api/memory-review/calendar-candidates", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  })

  if (!response.ok) {
    return
  }

  const payload = await response.json()
  const items = Array.isArray(payload?.items) ? payload.items : []
  const events = (items as RawCalendarItem[])
    .map(normalizeCalendarEvent)
    .filter(Boolean) as CalendarEvent[]

  events.sort((a, b) => calendarSortKey(a).localeCompare(calendarSortKey(b)))
  writeSnapshot<CalendarEvent[]>(scopedKey(userId, "calendar"), events)
}

async function loadMemoryHealthStatus(): Promise<MemoryHealthSchedulerStatus | null> {
  try {
    const schedulerRes = await fetch("/api/memory-review/quality/scheduler/status", {
      cache: "no-store",
    })

    if (schedulerRes.ok) {
      const schedulerJson = (await schedulerRes.json()) as MemoryHealthSchedulerStatus

      if (typeof schedulerJson.user_summary?.needs_review === "number") {
        return {
          ...schedulerJson,
          health_source: "scheduler",
        }
      }
    }

    const liveRes = await fetch("/api/memory-review/quality", {
      cache: "no-store",
    })

    if (!liveRes.ok) {
      return null
    }

    const liveJson = (await liveRes.json()) as MemoryQualityPayload

    return {
      health_source: "live",
      user_summary: {
        needs_review: liveJson.summary.needs_review,
        duplicate_groups: liveJson.summary.duplicate_groups,
        conflict_groups: liveJson.summary.conflict_groups,
        low_quality_memories: liveJson.summary.low_quality_memories,
        stale_memories: liveJson.summary.stale_memories || 0,
      },
    }
  } catch {
    return null
  }
}

async function prewarmMemories(userId: string) {
  const [dataResult, qualityResult, healthResult] = await Promise.allSettled([
    fetch("/api/memory-review?include_archived=true", {
      cache: "no-store",
    }).then(async (res) => (res.ok ? ((await res.json()) as MemoryReviewPayload) : null)),
    fetch("/api/memory-review/quality", {
      cache: "no-store",
    }).then(async (res) => (res.ok ? ((await res.json()) as MemoryQualityPayload) : null)),
    loadMemoryHealthStatus(),
  ])

  const payload: MemoriesSnapshotData = {
    data: dataResult.status === "fulfilled" ? dataResult.value : null,
    quality: qualityResult.status === "fulfilled" ? qualityResult.value : null,
    memoryHealthStatus: healthResult.status === "fulfilled" ? healthResult.value : null,
  }

  writeSnapshot<MemoriesSnapshotData>(scopedKey(userId, "memories"), payload)
}

async function runPrewarmQueue(userId: string) {
  const tasks = [
    () => prewarmCalendar(userId),
    () => prewarmPeople(userId),
    () => prewarmGoals(userId),
    () => prewarmMemories(userId),
  ]

  for (const task of tasks) {
    try {
      await task()
    } catch (error) {
      console.warn("Snapshot prewarm failed", error)
    }
  }
}

export function SnapshotPrewarmer({ userId }: { userId: string }) {
  useEffect(() => {
    if (!userId) {
      return
    }

    let cancelled = false
    let timeoutHandle: ReturnType<typeof setTimeout> | null = null
    let idleHandle: number | null = null

    const run = () => {
      if (cancelled) {
        return
      }

      void runPrewarmQueue(userId)
    }

    const idleWindow = window as IdleWindow

    if (idleWindow.requestIdleCallback) {
      idleHandle = idleWindow.requestIdleCallback(run, { timeout: 5000 })
    } else {
      timeoutHandle = setTimeout(run, 2000)
    }

    return () => {
      cancelled = true

      if (idleHandle != null && idleWindow.cancelIdleCallback) {
        idleWindow.cancelIdleCallback(idleHandle)
      }

      if (timeoutHandle) {
        clearTimeout(timeoutHandle)
      }
    }
  }, [userId])

  return null
}
