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
import { type CalendarEvent, type RawCalendarItem, calendarSnapshotKeyForUser, normalizeCalendarEvent, sortCalendarEvents, writeCalendarEventsSnapshot } from "@/lib/calendar-snapshot"

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

const SNAPSHOT_PREWARM_INTERVAL_MS = 15 * 60 * 1000

function prewarmMarkerKey(userId: string): string {
  return `app:snapshot-prewarm:${userId}:last-run`
}

function shouldRunPrewarm(userId: string): boolean {
  if (typeof window === "undefined") {
    return false
  }

  const raw = window.localStorage.getItem(prewarmMarkerKey(userId))
  if (!raw) {
    return true
  }

  const lastRun = Number(raw)
  if (!Number.isFinite(lastRun)) {
    return true
  }

  return Date.now() - lastRun > SNAPSHOT_PREWARM_INTERVAL_MS
}

function markPrewarmStarted(userId: string) {
  if (typeof window === "undefined") {
    return
  }

  try {
    window.localStorage.setItem(prewarmMarkerKey(userId), String(Date.now()))
  } catch {
    // Ignore storage failures.
  }
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

  // Non-destructive rule:
  // goals are the primary payload. If they fail, do not overwrite a good
  // existing snapshot with empty arrays from a partial prewarm failure.
  if (goalsResult.status !== "fulfilled") {
    return
  }

  const payload: GoalsSnapshotData = {
    filter: "active",
    goals: goalsResult.value,
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

  events.sort(sortCalendarEvents)
  writeCalendarEventsSnapshot(events, calendarSnapshotKeyForUser(userId))
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

  // Non-destructive rule:
  // memory-review is the primary payload. If it fails or returns null, do not
  // overwrite a good existing Memories snapshot with empty/null data.
  if (dataResult.status !== "fulfilled" || !dataResult.value) {
    return
  }

  const payload: MemoriesSnapshotData = {
    data: dataResult.value,
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

      if (!shouldRunPrewarm(userId)) {
        return
      }

      markPrewarmStarted(userId)
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
