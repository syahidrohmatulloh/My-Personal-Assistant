"use client"

import { useEffect, useMemo, useState } from "react"
import { BackToLastChat } from "@/components/navigation/back-to-last-chat";

import { useUserOwnedLabel } from "@/hooks/use-identity-owned-label"
import { createClient } from "@/lib/supabase/client"
import { type CalendarEvent, type RawCalendarItem, CALENDAR_SNAPSHOT_INVALIDATED_EVENT, calendarSnapshotKeyForUser, LEGACY_CALENDAR_EVENTS_CACHE_KEY, normalizeCalendarEvent, readCalendarEventsSnapshot, sortCalendarEvents as sortEvents, writeCalendarEventsSnapshot } from "@/lib/calendar-snapshot"




type TimelineRow =
  | {
      type: "event"
      event: CalendarEvent
      warning?: string
      previousEvent?: CalendarEvent
    }
  | {
      type: "free"
      id: string
      minutes: number
      startAt: string
      endAt: string
    }






function formatDate(date: string): string {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) {
    return date
  }

  return new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(parsed)
}

function formatTime(value: string | null): string | null {
  if (!value) {
    return null
  }

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) {
    return value
  }

  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed)
}

function minutesBetween(start: string | null, end: string | null): number | null {
  if (!start || !end) {
    return null
  }

  const startTime = new Date(start).getTime()
  const endTime = new Date(end).getTime()

  if (Number.isNaN(startTime) || Number.isNaN(endTime)) {
    return null
  }

  return Math.round((endTime - startTime) / 60000)
}

function durationLabel(minutes: number): string {
  if (minutes < 60) {
    return `${minutes} menit`
  }

  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60

  if (!mins) {
    return `${hours} jam`
  }

  return `${hours} jam ${mins} menit`
}

function eventTimeLabel(event: CalendarEvent): string {
  if (event.allDay || (!event.startAt && !event.endAt)) {
    return "Sepanjang hari"
  }

  const start = formatTime(event.startAt)
  const end = formatTime(event.endAt)

  if (start && end) {
    return `${start}–${end}`
  }

  return start || end || "Waktu belum tersedia"
}











function groupByDate(events: CalendarEvent[]): Array<[string, CalendarEvent[]]> {
  const grouped = new Map<string, CalendarEvent[]>()

  for (const event of [...events].sort(sortEvents)) {
    const existing = grouped.get(event.date) || []
    existing.push(event)
    grouped.set(event.date, existing)
  }

  return Array.from(grouped.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, items]) => [date, items.sort(sortEvents)])
}

function buildTimelineRows(events: CalendarEvent[]): TimelineRow[] {
  const rows: TimelineRow[] = []

  events.forEach((event, index) => {
    const previous = events[index - 1]
    let warning: string | undefined

    if (previous?.endAt && event.startAt) {
      const gap = minutesBetween(previous.endAt, event.startAt)

      if (gap !== null) {
        if (gap >= 60) {
          rows.push({
            type: "free",
            id: `${previous.id}-${event.id}-free`,
            minutes: gap,
            startAt: previous.endAt,
            endAt: event.startAt,
          })
        } else if (gap >= 0 && gap <= 20) {
          warning = `Hanya berjarak ${durationLabel(gap)} dari acara sebelumnya.`
        } else if (gap < 0) {
          warning = "Jadwal ini overlap dengan acara sebelumnya."
        }
      }
    }

    rows.push({ type: "event", event, warning, previousEvent: warning ? previous : undefined })
  })

  return rows
}

function timeRangeColumn(event: CalendarEvent): { start: string; end: string } {
  if (event.allDay || (!event.startAt && !event.endAt)) {
    return { start: "All day", end: "" }
  }

  return {
    start: formatTime(event.startAt) || "—",
    end: formatTime(event.endAt) || "",
  }
}


const CALENDAR_CHAT_HANDOFF_DRAFT_KEY = "app:calendar-chat-handoff-draft"
const LAST_CHAT_PATH_KEY = "app:last-chat-path"

function buildRescheduleHandoffDraft(event: CalendarEvent, warning: string, previousEvent?: CalendarEvent): string {
  const previousText = previousEvent
    ? `Acara sebelumnya: ${previousEvent.title} (${eventTimeLabel(previousEvent)}). `
    : ""

  return [
    "Beb, tolong bantu atur ulang jadwalku yang mepet di Calendar.",
    previousText,
    `Acara yang bermasalah: ${event.title} (${eventTimeLabel(event)}).`,
    `Warning: ${warning}`,
    "Tolong bantu carikan opsi waktu yang lebih masuk akal dan kalau perlu bantu update event-nya.",
  ]
    .join(" ")
    .replace(/\s+/g, " ")
    .trim()
}

function handoffCalendarWarningToChat(event: CalendarEvent, warning: string, previousEvent?: CalendarEvent) {
  if (typeof window === "undefined") {
    return
  }

  const draft = buildRescheduleHandoffDraft(event, warning, previousEvent)
  window.localStorage.setItem(CALENDAR_CHAT_HANDOFF_DRAFT_KEY, draft)

  const lastChatPath = window.localStorage.getItem(LAST_CHAT_PATH_KEY)
  const target = lastChatPath && lastChatPath.startsWith("/chat/")
    ? lastChatPath
    : "/chat"

  window.location.assign(target)
}


function StatusDot({ status }: { status: CalendarEvent["status"] }) {
  const className =
    status === "synced_google"
      ? "bg-emerald-500 shadow-[0_0_0_4px_rgba(16,185,129,0.12)]"
      : "bg-indigo-500 shadow-[0_0_0_4px_rgba(99,102,241,0.12)]"

  return <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${className}`} />
}

export default function CalendarPage() {
  const calendarEyebrow = useUserOwnedLabel("Calendar")
  const [snapshotKey, setSnapshotKey] = useState(LEGACY_CALENDAR_EVENTS_CACHE_KEY)
  const [events, setEvents] = useState<CalendarEvent[]>(() => readCalendarEventsSnapshot())
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  async function loadCalendarEvents() {
    setIsLoading(true)
    setError(null)

    try {
      const response = await fetch("/api/memory-review/calendar-candidates", {
        method: "GET",
        credentials: "include",
        cache: "no-store",
      })

      if (!response.ok) {
        throw new Error(`Calendar request failed: ${response.status}`)
      }

      const data = await response.json()
      const items = Array.isArray(data?.items) ? data.items : []
      const normalized = items
        .map((item: RawCalendarItem) => normalizeCalendarEvent(item))
        .filter(Boolean) as CalendarEvent[]

      const sortedEvents = normalized.sort(sortEvents)
      setEvents(sortedEvents)
      writeCalendarEventsSnapshot(sortedEvents, snapshotKey)
    } catch (err) {
      const message = err instanceof Error ? err.message : "Failed to load Calendar"
      setError(message)
    } finally {
      setIsLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function resolveUserScopedSnapshotKey() {
      const supabase = createClient()
      const {
        data: { session },
      } = await supabase.auth.getSession()

      if (cancelled) return

      const userId = session?.user?.id
      if (!userId) return

      const scopedKey = calendarSnapshotKeyForUser(userId)
      const scopedEvents = readCalendarEventsSnapshot(scopedKey)

      if (scopedEvents.length > 0) {
        setEvents(scopedEvents)
      } else if (events.length > 0) {
        writeCalendarEventsSnapshot(events, scopedKey)
      }

      setSnapshotKey(scopedKey)
    }

    void resolveUserScopedSnapshotKey()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    void loadCalendarEvents()
  }, [snapshotKey])

  useEffect(() => {
    function handleCalendarSnapshotInvalidated() {
      void loadCalendarEvents()
    }

    window.addEventListener(CALENDAR_SNAPSHOT_INVALIDATED_EVENT, handleCalendarSnapshotInvalidated)

    return () => {
      window.removeEventListener(CALENDAR_SNAPSHOT_INVALIDATED_EVENT, handleCalendarSnapshotInvalidated)
    }
  }, [snapshotKey])

  const groupedEvents = useMemo(() => groupByDate(events), [events])

  return (
    <main className="min-h-screen bg-bg px-4 py-6 text-fg sm:px-6 lg:px-8">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <header className="overflow-hidden rounded-3xl border border-border bg-fg/[0.035] p-5 shadow-sm sm:p-6">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-fg-muted">
                {calendarEyebrow}
              </p>
              <h1 className="mt-2 text-3xl font-semibold tracking-tight sm:text-4xl">
                Calendar
              </h1>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-fg-muted">
                Timeline agenda terkonfirmasi. Saran jadwal yang belum kamu setujui tetap diproses lewat chat.
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void loadCalendarEvents()}
                className="inline-flex h-10 items-center justify-center rounded-full border border-border bg-bg px-4 text-sm font-medium text-fg shadow-sm transition hover:bg-fg/5 disabled:cursor-not-allowed disabled:opacity-60"
                disabled={isLoading}
              >
                {isLoading ? "Refreshing..." : "Refresh"}
              </button>
              <BackToLastChat className="inline-flex h-10 items-center justify-center rounded-full border border-border bg-fg px-4 text-sm font-medium text-bg shadow-sm transition hover:opacity-90">
                Back to chat
              </BackToLastChat>
            </div>
          </div>
        </header>

        <section className="grid gap-4 sm:grid-cols-3">
          <div className="rounded-3xl border border-border bg-fg/[0.035] p-5">
            <p className="text-sm text-fg-muted">Total events</p>
            <p className="mt-2 text-3xl font-semibold">{events.length}</p>
          </div>
          <div className="rounded-3xl border border-border bg-fg/[0.035] p-5">
            <p className="text-sm text-fg-muted">Google synced</p>
            <p className="mt-2 text-3xl font-semibold">
              {events.filter((event) => event.status === "synced_google").length}
            </p>
          </div>
          <div className="rounded-3xl border border-border bg-fg/[0.035] p-5">
            <p className="text-sm text-fg-muted">Local only</p>
            <p className="mt-2 text-3xl font-semibold">
              {events.filter((event) => event.status === "confirmed_local").length}
            </p>
          </div>
        </section>

        <section className="rounded-3xl border border-border bg-fg/[0.035] p-4 shadow-sm sm:p-6">
          <div className="mb-5 flex flex-col gap-1">
            <h2 className="text-xl font-semibold">Agenda terjadwal</h2>
            <p className="text-sm text-fg-muted">
              Mini timeline ini membantu melihat urutan acara, jeda waktu senggang, dan jadwal yang terlalu mepet.
            </p>
            {isLoading && groupedEvents.length > 0 ? (
              <p className="text-xs text-fg-muted/80">Refreshing latest schedule…</p>
            ) : null}
          </div>

          {error ? (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/10 p-4 text-sm text-red-600 dark:text-red-300">
              {error}
            </div>
          ) : null}

          {isLoading && groupedEvents.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border p-8 text-center text-sm text-fg-muted">
              Loading Calendar...
            </div>
          ) : !error && groupedEvents.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-border p-10 text-center">
              <p className="text-base font-medium">Belum ada event terkonfirmasi.</p>
              <p className="mt-2 text-sm text-fg-muted">
                Coba sebutkan agenda di chat. Aliyya akan tanya dulu sebelum memasukkannya ke Calendar.
              </p>
            </div>
          ) : (
            <div className="space-y-8">
              {groupedEvents.map(([date, items]) => (
                <div key={date} className="space-y-3">
                  <div className="px-1 py-1">
                    <h3 className="text-xs font-semibold uppercase tracking-[0.18em] text-indigo-500 dark:text-indigo-300">
                      {formatDate(date)}
                    </h3>
                  </div>

                  <div className="ml-1 border-l border-border/70 pl-4 sm:ml-3 sm:pl-5">
                    {buildTimelineRows(items).map((row) => {
                      if (row.type === "free") {
                        return (
                          <div
                            key={row.id}
                            className="relative my-1 flex items-center rounded-r-2xl border-y border-dashed border-border/50 bg-fg/[0.018] px-1.5 py-2 sm:px-2 sm:py-2.5"
                          >
                            <span className="absolute -left-[21px] top-1/2 h-2 w-2 -translate-y-1/2 rounded-full border border-border bg-bg sm:-left-[25px]" />

                            <div className="w-14 shrink-0 pr-3 text-right font-mono text-[10px] leading-5 text-fg-muted/75 sm:w-24 sm:pr-0 sm:text-left sm:text-[11px]">
                              <div>{formatTime(row.startAt)}</div>
                              <div>{formatTime(row.endAt)}</div>
                            </div>

                            <div className="flex min-w-0 items-center gap-2 text-[11px] italic text-fg-muted sm:text-xs">
                              <span className="rounded-md border border-border/70 bg-bg/60 px-1.5 py-0.5 not-italic sm:px-2">
                                💤
                              </span>
                              <span className="break-words">{durationLabel(row.minutes)} kosong</span>
                            </div>
                          </div>
                        )
                      }

                      const { event, warning, previousEvent } = row
                      const time = timeRangeColumn(event)

                      return (
                        <article
                          key={event.id}
                          className="group relative rounded-r-2xl border-b border-border/60 px-2 py-3 transition hover:bg-fg/[0.025]"
                        >
                          <span className="absolute -left-[22px] top-5 sm:-left-[26px]">
                            <StatusDot status={event.status} />
                          </span>

                          <div className="flex items-start gap-4 sm:gap-3">
                            <div className="w-14 shrink-0 pr-3 text-right font-mono text-[10px] leading-5 text-fg-muted/75 sm:w-24 sm:pr-0 sm:text-left sm:text-[11px]">
                              <div className="font-semibold text-fg/80 tabular-nums">{time.start}</div>
                              {time.end ? (
                                <div className="text-fg-muted/65 tabular-nums">{time.end}</div>
                              ) : null}
                            </div>

                            <div className="min-w-0 flex-1">
                              <div className="flex items-start justify-between gap-3">
                                <div className="min-w-0">
                                  <div className="flex min-w-0 flex-wrap items-center gap-2">
                                    <h4 className="min-w-0 break-words text-sm font-medium leading-snug text-fg/90 transition group-hover:text-fg sm:text-[15px]">
                                      {event.title}
                                    </h4>
                                    <span className="shrink-0 font-mono text-[10px] uppercase tracking-wide text-fg-muted/75">
                                      {event.status === "synced_google" ? "Google" : "Local"}
                                    </span>
                                  </div>

                                  {event.location ? (
                                    <p className="mt-0.5 min-w-0 break-words text-[11px] leading-4 text-fg-muted/75">
                                      {event.location}
                                    </p>
                                  ) : null}

                                  {event.syncError ? (
                                    <p className="mt-2 inline-flex rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-700 dark:text-amber-300">
                                      Sync note: {event.syncError}
                                    </p>
                                  ) : null}

                                  {warning ? (
                                    <div className="mt-2 flex flex-col items-start gap-1.5">
                                      <p className="inline-flex items-center gap-1.5 rounded-md border border-amber-500/20 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-700 dark:text-amber-300">
                                        <span>⚠️</span>
                                        <span>{warning}</span>
                                      </p>
                                      <button
                                        type="button"
                                        onClick={() => handoffCalendarWarningToChat(event, warning, previousEvent)}
                                        className="inline-flex items-center gap-1 rounded-md border border-border bg-fg/[0.035] px-2 py-1 text-[11px] font-medium text-fg-muted transition hover:bg-fg/5 hover:text-fg"
                                      >
                                        <span>🤖</span>
                                        <span>Bantu Atur Ulang</span>
                                      </button>
                                    </div>
                                  ) : null}
                                </div>

                                {event.googleLink ? (
                                  <a
                                    href={event.googleLink}
                                    target="_blank"
                                    rel="noreferrer"
                                    className="hidden h-8 shrink-0 items-center justify-center rounded-lg border border-border bg-fg/[0.035] px-3 text-xs font-medium text-fg-muted shadow-sm transition hover:bg-fg/5 hover:text-fg sm:inline-flex"
                                  >
                                    Open Google
                                  </a>
                                ) : null}
                              </div>

                              {event.googleLink ? (
                                <a
                                  href={event.googleLink}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="mt-1 inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 transition hover:text-emerald-500 dark:text-emerald-300 dark:hover:text-emerald-200 sm:hidden"
                                >
                                  <span>Open Google</span>
                                  <span aria-hidden="true">↗</span>
                                </a>
                              ) : null}
                            </div>
                          </div>
                        </article>
                      )
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}
