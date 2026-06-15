"use client"

import {
  ArrowUpRight,
  Bot,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  Clock3,
  ExternalLink,
  Filter,
  Loader2,
  MapPin,
  RefreshCcw,
  Sparkles,
  Sunrise,
  Zap,
} from "lucide-react"
import { useEffect, useMemo, useState } from "react"

import { createClient } from "@/lib/supabase/client"
import {
  type CalendarEvent,
  CALENDAR_SNAPSHOT_INVALIDATED_EVENT,
  LEGACY_CALENDAR_EVENTS_CACHE_KEY,
  buildCalendarReadRange,
  calendarSnapshotKeyForUser,
  loadMergedCalendarEvents,
  readCalendarEventsSnapshot,
  sortCalendarEvents,
  writeCalendarEventsSnapshot,
} from "@/lib/calendar-snapshot"

type ViewFilter = "today" | "upcoming" | "all"
type SourceFilter = "all" | "aliyya" | "google"

type AgendaGroup = {
  date: string
  events: CalendarEvent[]
}

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

const GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/u/0/r"
const CALENDAR_CHAT_HANDOFF_DRAFT_KEY = "app:calendar-chat-handoff-draft"
const LAST_CHAT_PATH_KEY = "app:last-chat-path"

function localDateKey(date = new Date()): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, "0")
  const day = String(date.getDate()).padStart(2, "0")
  return `${year}-${month}-${day}`
}

function formatDate(date: string): string {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return date

  return new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(parsed)
}

function formatCompactDate(date: string): string {
  const parsed = new Date(`${date}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return date

  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
  }).format(parsed)
}

function formatTime(value: string | null): string | null {
  if (!value) return null

  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value

  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(parsed)
}

function minutesBetween(start: string | null, end: string | null): number | null {
  if (!start || !end) return null

  const startTime = new Date(start).getTime()
  const endTime = new Date(end).getTime()

  if (Number.isNaN(startTime) || Number.isNaN(endTime)) return null

  return Math.round((endTime - startTime) / 60000)
}

function durationLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} menit`

  const hours = Math.floor(minutes / 60)
  const mins = minutes % 60

  if (!mins) return `${hours} jam`

  return `${hours} jam ${mins} menit`
}

function eventTimeLabel(event: CalendarEvent): string {
  if (event.allDay || (!event.startAt && !event.endAt)) return "Sepanjang hari"

  const start = formatTime(event.startAt)
  const end = formatTime(event.endAt)

  if (start && end) return `${start}–${end}`

  return start || end || "Waktu belum tersedia"
}

function timeColumn(event: CalendarEvent): { start: string; end: string } {
  if (event.allDay || (!event.startAt && !event.endAt)) {
    return { start: "All day", end: "" }
  }

  return {
    start: formatTime(event.startAt) || "—",
    end: formatTime(event.endAt) || "",
  }
}

function sourceMeta(event: CalendarEvent): {
  label: string
  helper: string
  badgeClass: string
  dotClass: string
} {
  if (event.source === "google") {
    return {
      label: "Google",
      helper: "Direct Google event",
      badgeClass: "border-emerald-200 bg-emerald-50 text-emerald-700",
      dotClass: "bg-emerald-500 shadow-[0_0_0_5px_rgba(16,185,129,0.12)]",
    }
  }

  if (event.source === "synced") {
    return {
      label: "Synced",
      helper: "Aliyya + Google",
      badgeClass: "border-lime-200 bg-lime-50 text-lime-700",
      dotClass: "bg-lime-500 shadow-[0_0_0_5px_rgba(132,204,22,0.14)]",
    }
  }

  return {
    label: "Local",
    helper: "Aliyya Calendar",
    badgeClass: "border-indigo-200 bg-indigo-50 text-indigo-700",
    dotClass: "bg-indigo-500 shadow-[0_0_0_5px_rgba(99,102,241,0.13)]",
  }
}

function sourceMatches(event: CalendarEvent, source: SourceFilter): boolean {
  if (source === "all") return true
  if (source === "google") return event.source === "google"
  return event.source === "local" || event.source === "synced"
}

function viewMatches(event: CalendarEvent, view: ViewFilter, today: string): boolean {
  if (view === "all") return true
  if (view === "today") return event.date === today
  return event.date >= today
}

function groupEvents(events: CalendarEvent[]): AgendaGroup[] {
  const grouped = new Map<string, CalendarEvent[]>()

  for (const event of [...events].sort(sortCalendarEvents)) {
    const rows = grouped.get(event.date) || []
    rows.push(event)
    grouped.set(event.date, rows)
  }

  return Array.from(grouped.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, items]) => ({
      date,
      events: items.sort(sortCalendarEvents),
    }))
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
          warning = `Jeda hanya ${durationLabel(gap)} dari agenda sebelumnya.`
        } else if (gap < 0) {
          warning = "Jadwal ini overlap dengan agenda sebelumnya."
        }
      }
    }

    rows.push({ type: "event", event, warning, previousEvent: warning ? previous : undefined })
  })

  return rows
}

function handoffCalendarActionToChat(event: CalendarEvent, mode: "sync" | "reschedule", warning?: string) {
  if (typeof window === "undefined") return

  const draft =
    mode === "sync"
      ? [
          `Tolong sync agenda ini ke Google Calendar: ${event.title}.`,
          `Tanggal: ${formatDate(event.date)}.`,
          `Waktu: ${eventTimeLabel(event)}.`,
          event.location ? `Lokasi: ${event.location}.` : "",
        ]
          .join(" ")
          .replace(/\s+/g, " ")
          .trim()
      : [
          "Tolong bantu atur ulang jadwalku yang mepet di Calendar.",
          `Agenda: ${event.title} (${eventTimeLabel(event)}).`,
          warning ? `Warning: ${warning}.` : "",
          "Tolong bantu carikan opsi waktu yang lebih masuk akal dan kalau perlu bantu update event-nya.",
        ]
          .join(" ")
          .replace(/\s+/g, " ")
          .trim()

  window.localStorage.setItem(CALENDAR_CHAT_HANDOFF_DRAFT_KEY, draft)

  window.localStorage.getItem(LAST_CHAT_PATH_KEY)
  window.location.assign("/chat-v2")
}

function StatCard({
  label,
  value,
  helper,
}: {
  label: string
  value: number | string
  helper: string
}) {
  return (
    <div className="rounded-[1.75rem] border border-white/70 bg-white/55 p-4 shadow-sm backdrop-blur-xl">
      <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-400">
        {label}
      </p>
      <p className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-stone-950">
        {value}
      </p>
      <p className="mt-1 text-xs leading-5 text-stone-500">{helper}</p>
    </div>
  )
}

function FilterPill({
  active,
  children,
  onClick,
}: {
  active: boolean
  children: React.ReactNode
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "rounded-full px-3 py-1.5 text-xs font-semibold transition active:scale-[0.98]",
        active
          ? "bg-stone-950 text-white shadow-sm"
          : "border border-stone-200 bg-white/60 text-stone-500 hover:bg-white hover:text-stone-950",
      ].join(" ")}
    >
      {children}
    </button>
  )
}

function EventCard({
  event,
  warning,
  previousEvent,
}: {
  event: CalendarEvent
  warning?: string
  previousEvent?: CalendarEvent
}) {
  const time = timeColumn(event)
  const meta = sourceMeta(event)
  const hasGoogleLink = Boolean(event.googleLink)

  return (
    <article className="group relative overflow-hidden rounded-[1.6rem] border border-white/70 bg-white/62 p-4 shadow-sm backdrop-blur-xl transition hover:-translate-y-0.5 hover:bg-white/75 hover:shadow-md">
      <div className="pointer-events-none absolute inset-y-0 left-0 w-1 bg-gradient-to-b from-stone-900/20 via-stone-900/5 to-transparent opacity-60" />

      <div className="flex gap-4">
        <div className="w-16 shrink-0 pt-0.5 font-mono text-[11px] leading-5 text-stone-500">
          <div className="font-semibold text-stone-950 tabular-nums">{time.start}</div>
          {time.end ? <div className="tabular-nums text-stone-400">{time.end}</div> : null}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className={`mt-0.5 h-2.5 w-2.5 rounded-full ${meta.dotClass}`} />
                <h3 className="min-w-0 break-words text-base font-semibold leading-snug tracking-[-0.02em] text-stone-950">
                  {event.title}
                </h3>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${meta.badgeClass}`}>
                  {meta.label}
                </span>
                <span className="text-[11px] text-stone-400">{meta.helper}</span>
              </div>
            </div>

            <ChevronRight className="mt-1 h-4 w-4 shrink-0 text-stone-300 transition group-hover:translate-x-0.5 group-hover:text-stone-500" />
          </div>

          {event.location ? (
            <p className="mt-3 flex items-center gap-1.5 text-sm leading-5 text-stone-500">
              <MapPin className="h-3.5 w-3.5 shrink-0" />
              <span className="min-w-0 break-words">{event.location}</span>
            </p>
          ) : null}

          {event.syncError ? (
            <p className="mt-3 rounded-2xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-700">
              Sync note: {event.syncError}
            </p>
          ) : null}

          {warning ? (
            <div className="mt-3 rounded-2xl border border-orange-200 bg-orange-50/85 p-3">
              <p className="text-xs font-medium leading-5 text-orange-800">{warning}</p>
              <button
                type="button"
                onClick={() => handoffCalendarActionToChat(event, "reschedule", warning)}
                className="mt-2 inline-flex items-center gap-1.5 rounded-full border border-orange-200 bg-white/70 px-3 py-1.5 text-xs font-semibold text-orange-700 transition hover:bg-white"
              >
                <Bot className="h-3.5 w-3.5" />
                Bantu atur ulang
              </button>
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap gap-2">
            {hasGoogleLink ? (
              <a
                href={event.googleLink || GOOGLE_CALENDAR_URL}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-full border border-stone-200 bg-white/80 px-3 py-1.5 text-xs font-semibold text-stone-700 shadow-sm transition hover:bg-white hover:text-stone-950"
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open Google
              </a>
            ) : null}

            {event.source === "local" ? (
              <button
                type="button"
                onClick={() => handoffCalendarActionToChat(event, "sync")}
                className="inline-flex items-center gap-1.5 rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1.5 text-xs font-semibold text-indigo-700 transition hover:bg-indigo-100"
              >
                <Sparkles className="h-3.5 w-3.5" />
                Ask Aliyya to sync
              </button>
            ) : null}

            {previousEvent ? (
              <span className="inline-flex items-center gap-1.5 rounded-full border border-stone-200 bg-white/55 px-3 py-1.5 text-xs text-stone-500">
                <Clock3 className="h-3.5 w-3.5" />
                After {previousEvent.title}
              </span>
            ) : null}
          </div>
        </div>
      </div>
    </article>
  )
}

function FreeTimeRow({ row }: { row: Extract<TimelineRow, { type: "free" }> }) {
  return (
    <div className="rounded-[1.4rem] border border-dashed border-stone-200 bg-white/35 px-4 py-3 text-sm text-stone-500 backdrop-blur">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-mono text-xs tabular-nums text-stone-400">
          {formatTime(row.startAt)}–{formatTime(row.endAt)}
        </span>
        <span className="rounded-full border border-white/70 bg-white/65 px-2.5 py-1 text-[11px] font-semibold text-stone-500">
          {durationLabel(row.minutes)} kosong
        </span>
      </div>
    </div>
  )
}

export default function CalendarPage() {
  const [snapshotKey, setSnapshotKey] = useState(LEGACY_CALENDAR_EVENTS_CACHE_KEY)
  const [events, setEvents] = useState<CalendarEvent[]>(() => readCalendarEventsSnapshot())
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewFilter, setViewFilter] = useState<ViewFilter>("upcoming")
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all")

  const today = localDateKey()

  async function loadCalendarEvents() {
    setIsLoading(true)
    setError(null)

    try {
      const range = buildCalendarReadRange({
        daysBefore: 7,
        daysAfter: 45,
      })
      const mergedEvents = await loadMergedCalendarEvents(range)

      setEvents(mergedEvents)
      writeCalendarEventsSnapshot(mergedEvents, snapshotKey)
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    void loadCalendarEvents()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotKey])

  useEffect(() => {
    function handleCalendarSnapshotInvalidated() {
      void loadCalendarEvents()
    }

    window.addEventListener(CALENDAR_SNAPSHOT_INVALIDATED_EVENT, handleCalendarSnapshotInvalidated)

    return () => {
      window.removeEventListener(CALENDAR_SNAPSHOT_INVALIDATED_EVENT, handleCalendarSnapshotInvalidated)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [snapshotKey])

  const filteredEvents = useMemo(() => {
    return events
      .filter((event) => viewMatches(event, viewFilter, today))
      .filter((event) => sourceMatches(event, sourceFilter))
      .sort(sortCalendarEvents)
  }, [events, sourceFilter, today, viewFilter])

  const groupedEvents = useMemo(() => groupEvents(filteredEvents), [filteredEvents])
  const todaysEvents = useMemo(
    () => events.filter((event) => event.date === today).sort(sortCalendarEvents),
    [events, today],
  )
  const nextEvent = filteredEvents.find((event) => event.date >= today) || filteredEvents[0] || null

  const localCount = events.filter((event) => event.source === "local").length
  const syncedCount = events.filter((event) => event.source === "synced").length
  const googleCount = events.filter((event) => event.source === "google").length

  return (
    <main className="relative h-[100dvh] overflow-hidden bg-[#f7f3ea] px-4 py-4 text-stone-950 sm:px-6 lg:px-8">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_16%,rgba(244,194,194,0.42),transparent_28rem),radial-gradient(circle_at_78%_12%,rgba(206,220,183,0.36),transparent_30rem),radial-gradient(circle_at_48%_92%,rgba(235,224,166,0.34),transparent_34rem)]" />
        <div className="absolute -left-24 bottom-[-12rem] h-[34rem] w-[34rem] rounded-full bg-lime-200/25 blur-[120px]" />
        <div className="absolute -right-28 top-24 h-[36rem] w-[36rem] rounded-full bg-rose-200/25 blur-[130px]" />
      </div>

      <div className="relative mx-auto flex h-full w-full max-w-7xl flex-col gap-4">
        <header className="shrink-0 flex flex-col gap-3 rounded-[2rem] border border-white/70 bg-white/48 p-4 shadow-sm backdrop-blur-xl sm:flex-row sm:items-start sm:justify-between sm:p-5">
          <div>
            <p className="inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white/60 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-500 shadow-sm">
              <Sparkles className="h-3.5 w-3.5" />
              Calendar command center
            </p>
            <h1 className="mt-4 text-4xl font-semibold tracking-[-0.065em] text-stone-950 sm:text-5xl">
              Calendar
            </h1>
            <p className="mt-3 max-w-2xl text-sm leading-6 text-stone-600">
              A clean command deck for Aliyya events, Google Calendar sync, daily flow, and schedule gaps.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void loadCalendarEvents()}
              disabled={isLoading}
              className="inline-flex h-10 items-center gap-2 rounded-full border border-stone-200 bg-white/70 px-4 text-sm font-semibold text-stone-700 shadow-sm backdrop-blur transition hover:bg-white hover:text-stone-950 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
              {isLoading ? "Refreshing" : "Refresh"}
            </button>

            <a
              href={GOOGLE_CALENDAR_URL}
              target="_blank"
              rel="noreferrer"
              className="inline-flex h-10 items-center gap-2 rounded-full border border-stone-200 bg-white/70 px-4 text-sm font-semibold text-stone-700 shadow-sm backdrop-blur transition hover:bg-white hover:text-stone-950"
            >
              <ArrowUpRight className="h-4 w-4" />
              Google Calendar
            </a>

            <a
              href="/chat-v2"
              className="inline-flex h-10 items-center justify-center rounded-full bg-stone-950 px-4 text-sm font-semibold text-white shadow-sm transition hover:bg-stone-800"
            >
              Back to chat
            </a>
          </div>
        </header>

        <section className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[0.72fr_1.28fr]">
          <aside className="min-h-0 space-y-4 overflow-y-auto pr-1 xl:[scrollbar-width:thin]">
            <div className="rounded-[2rem] border border-white/70 bg-white/50 p-4 shadow-sm backdrop-blur-xl">
              <div className="flex items-center gap-3">
                <span className="grid h-11 w-11 place-items-center rounded-2xl bg-stone-950 text-white shadow-sm">
                  <Sunrise className="h-5 w-5" />
                </span>
                <div>
                  <p className="text-[11px] font-semibold uppercase tracking-[0.22em] text-stone-400">
                    Today
                  </p>
                  <p className="text-base font-semibold text-stone-950">
                    {formatDate(today)}
                  </p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                <StatCard label="Today" value={todaysEvents.length} helper="agenda" />
                <StatCard label="Synced" value={syncedCount} helper="Aliyya + Google" />
                <StatCard label="Local" value={localCount} helper="needs sync" />
              </div>
            </div>

            <div className="rounded-[2rem] border border-white/70 bg-white/50 p-4 shadow-sm backdrop-blur-xl">
              <div className="mb-4 flex items-center gap-2">
                <Filter className="h-4 w-4 text-stone-400" />
                <h2 className="font-semibold text-stone-950">View</h2>
              </div>

              <div className="flex flex-wrap gap-2">
                <FilterPill active={viewFilter === "today"} onClick={() => setViewFilter("today")}>
                  Today
                </FilterPill>
                <FilterPill active={viewFilter === "upcoming"} onClick={() => setViewFilter("upcoming")}>
                  Upcoming
                </FilterPill>
                <FilterPill active={viewFilter === "all"} onClick={() => setViewFilter("all")}>
                  All
                </FilterPill>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <FilterPill active={sourceFilter === "all"} onClick={() => setSourceFilter("all")}>
                  All source
                </FilterPill>
                <FilterPill active={sourceFilter === "aliyya"} onClick={() => setSourceFilter("aliyya")}>
                  Aliyya
                </FilterPill>
                <FilterPill active={sourceFilter === "google"} onClick={() => setSourceFilter("google")}>
                  Google
                </FilterPill>
              </div>
            </div>

            <div className="rounded-[2rem] border border-white/70 bg-white/50 p-5 shadow-sm backdrop-blur-xl">
              <div className="flex items-center gap-2">
                <Zap className="h-4 w-4 text-stone-400" />
                <h2 className="font-semibold text-stone-950">Next focus</h2>
              </div>

              {nextEvent ? (
                <div className="mt-4 rounded-3xl border border-white/70 bg-white/55 p-4">
                  <p className="text-xs font-semibold uppercase tracking-[0.18em] text-stone-400">
                    {formatCompactDate(nextEvent.date)} • {eventTimeLabel(nextEvent)}
                  </p>
                  <p className="mt-2 text-lg font-semibold tracking-[-0.03em] text-stone-950">
                    {nextEvent.title}
                  </p>
                  {nextEvent.location ? (
                    <p className="mt-1 text-sm text-stone-500">{nextEvent.location}</p>
                  ) : null}
                </div>
              ) : (
                <p className="mt-4 text-sm leading-6 text-stone-500">
                  No upcoming event in this view. Use chat to add a new agenda.
                </p>
              )}
            </div>

            <div className="rounded-[2rem] border border-white/70 bg-white/50 p-5 shadow-sm backdrop-blur-xl">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-stone-400" />
                <h2 className="font-semibold text-stone-950">Source health</h2>
              </div>
              <div className="mt-4 space-y-2 text-sm text-stone-600">
                <div className="flex items-center justify-between">
                  <span>Google events</span>
                  <span className="font-semibold text-stone-950">{googleCount}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Synced Aliyya events</span>
                  <span className="font-semibold text-stone-950">{syncedCount}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Local only</span>
                  <span className="font-semibold text-stone-950">{localCount}</span>
                </div>
              </div>
            </div>
          </aside>

          <section className="min-h-0 overflow-y-auto rounded-[2.25rem] border border-white/70 bg-white/45 p-4 shadow-xl shadow-stone-200/50 backdrop-blur-xl sm:p-5 xl:[scrollbar-width:thin]">
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-stone-400">
                  Agenda flow
                </p>
                <h2 className="mt-1 text-2xl font-semibold tracking-[-0.045em] text-stone-950">
                  {viewFilter === "today" ? "Today’s command deck" : viewFilter === "upcoming" ? "Upcoming timeline" : "All calendar events"}
                </h2>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-stone-500">
                  Events are merged from Aliyya local memory and Google Calendar, then deduped for a cleaner planning view.
                </p>
              </div>

              <div className="inline-flex items-center gap-2 rounded-full border border-stone-200 bg-white/60 px-3 py-1.5 text-xs font-semibold text-stone-500">
                <CalendarDays className="h-3.5 w-3.5" />
                {filteredEvents.length} shown
              </div>
            </div>

            {error ? (
              <div className="rounded-3xl border border-red-200 bg-red-50 p-4 text-sm leading-6 text-red-700">
                {error}
              </div>
            ) : null}

            {isLoading && groupedEvents.length === 0 ? (
              <div className="grid min-h-[28rem] place-items-center rounded-[2rem] border border-dashed border-stone-200 bg-white/35 text-center">
                <div>
                  <Loader2 className="mx-auto h-7 w-7 animate-spin text-stone-400" />
                  <p className="mt-3 text-sm font-medium text-stone-600">Loading Calendar...</p>
                </div>
              </div>
            ) : !error && groupedEvents.length === 0 ? (
              <div className="grid min-h-[28rem] place-items-center rounded-[2rem] border border-dashed border-stone-200 bg-white/35 p-8 text-center">
                <div>
                  <Sparkles className="mx-auto h-8 w-8 text-stone-400" />
                  <p className="mt-4 text-lg font-semibold text-stone-950">Belum ada agenda di view ini.</p>
                  <p className="mt-2 max-w-md text-sm leading-6 text-stone-500">
                    Coba sebutkan agenda di chat. Aliyya akan preview dulu sebelum memasukkannya ke Calendar.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                {isLoading ? (
                  <p className="rounded-full border border-white/70 bg-white/55 px-3 py-1.5 text-xs font-medium text-stone-500">
                    Refreshing latest schedule…
                  </p>
                ) : null}

                {groupedEvents.map((group) => (
                  <div key={group.date} className="space-y-3">
                    <div className="flex items-center justify-between gap-3 px-1">
                      <h3 className="text-xs font-semibold uppercase tracking-[0.22em] text-stone-400">
                        {formatDate(group.date)}
                      </h3>
                      <span className="text-xs text-stone-400">
                        {group.events.length} agenda
                      </span>
                    </div>

                    <div className="space-y-3">
                      {buildTimelineRows(group.events).map((row) => {
                        if (row.type === "free") {
                          return <FreeTimeRow key={row.id} row={row} />
                        }

                        return (
                          <EventCard
                            key={row.event.id}
                            event={row.event}
                            warning={row.warning}
                            previousEvent={row.previousEvent}
                          />
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>
        </section>
      </div>
    </main>
  )
}
