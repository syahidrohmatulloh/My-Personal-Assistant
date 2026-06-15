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
  X,
  Zap,
} from "lucide-react"
import { useEffect, useMemo, useState, type ReactNode } from "react"

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
type CalendarVisualMode = "life_companion" | "chief_of_staff"
type CalendarActionMode = "sync" | "reschedule" | "reminder"

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

function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ")
}

function readStoredCalendarVisualMode(): CalendarVisualMode {
  if (typeof window === "undefined") return "life_companion"

  const exactKeys = [
    "app:assistant-mode",
    "app:chat-v2-assistant-mode",
    "assistant_mode",
    "assistantMode",
    "companion_mode",
    "app:companion-mode",
  ]

  for (const key of exactKeys) {
    const value = String(window.localStorage.getItem(key) || "").toLowerCase()
    if (value.includes("chief_of_staff") || value === "chief") return "chief_of_staff"
    if (value.includes("life_companion") || value === "life") return "life_companion"
  }

  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index) || ""
    const value = window.localStorage.getItem(key) || ""
    const haystack = `${key} ${value}`.toLowerCase()

    if (
      (haystack.includes("chief_of_staff") || haystack.includes('"chief"')) &&
      /(assistant|companion|chat|mode)/i.test(key)
    ) {
      return "chief_of_staff"
    }

    if (
      (haystack.includes("life_companion") || haystack.includes('"life"')) &&
      /(assistant|companion|chat|mode)/i.test(key)
    ) {
      return "life_companion"
    }
  }

  return "life_companion"
}

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

function sourceMeta(
  event: CalendarEvent,
  isChief: boolean,
): {
  label: string
  helper: string
  badgeClass: string
  dotClass: string
} {
  if (event.source === "google") {
    return {
      label: "Google",
      helper: "Direct Google event",
      badgeClass: isChief
        ? "border-teal-300/25 bg-teal-300/[0.12] text-teal-100"
        : "border-emerald-200 bg-emerald-50 text-emerald-700",
      dotClass: isChief
        ? "bg-teal-300 shadow-[0_0_0_5px_rgba(94,234,212,0.12)]"
        : "bg-emerald-500 shadow-[0_0_0_5px_rgba(16,185,129,0.12)]",
    }
  }

  if (event.source === "synced") {
    return {
      label: "Synced",
      helper: "Aliyya + Google",
      badgeClass: isChief
        ? "border-lime-300/25 bg-lime-300/[0.12] text-lime-100"
        : "border-lime-200 bg-lime-50 text-lime-700",
      dotClass: isChief
        ? "bg-lime-300 shadow-[0_0_0_5px_rgba(190,242,100,0.12)]"
        : "bg-lime-500 shadow-[0_0_0_5px_rgba(132,204,22,0.14)]",
    }
  }

  return {
    label: "Local",
    helper: "Aliyya Calendar",
    badgeClass: isChief
      ? "border-violet-300/25 bg-violet-300/[0.12] text-violet-100"
      : "border-indigo-200 bg-indigo-50 text-indigo-700",
    dotClass: isChief
      ? "bg-violet-300 shadow-[0_0_0_5px_rgba(196,181,253,0.12)]"
      : "bg-indigo-500 shadow-[0_0_0_5px_rgba(99,102,241,0.13)]",
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

function handoffCalendarActionToChat(event: CalendarEvent, mode: CalendarActionMode, warning?: string) {
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
      : mode === "reminder"
        ? [
            `Tolong tambahkan pengingat 15 menit sebelum agenda ${event.title}.`,
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
  window.location.assign("/chat-v2")
}

function shellClass(isChief: boolean): string {
  return cn(
    "relative h-[100dvh] overflow-hidden px-4 py-4 sm:px-6 lg:px-8",
    isChief ? "bg-[#080d14] text-slate-100" : "bg-[#f7f3ea] text-stone-950",
  )
}

function Background({ isChief }: { isChief: boolean }) {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      {isChief ? (
        <>
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_72%_18%,rgba(45,212,191,0.16),transparent_30rem),radial-gradient(circle_at_18%_80%,rgba(59,130,246,0.08),transparent_32rem),radial-gradient(circle_at_88%_88%,rgba(180,130,58,0.06),transparent_26rem)]" />
          <div className="absolute inset-0 opacity-[0.045] [background-image:linear-gradient(rgba(148,163,184,0.32)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.24)_1px,transparent_1px)] [background-size:48px_48px]" />
          <div className="absolute right-[-8%] top-[4%] h-[42rem] w-[42rem] rounded-full bg-teal-300/[0.08] blur-[120px]" />
          <div className="absolute bottom-[-20%] left-[-14%] h-[44rem] w-[44rem] rounded-full bg-blue-400/[0.05] blur-[150px]" />
        </>
      ) : (
        <>
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_16%,rgba(244,194,194,0.42),transparent_28rem),radial-gradient(circle_at_78%_12%,rgba(206,220,183,0.36),transparent_30rem),radial-gradient(circle_at_48%_92%,rgba(235,224,166,0.34),transparent_34rem)]" />
          <div className="absolute -left-24 bottom-[-12rem] h-[34rem] w-[34rem] rounded-full bg-lime-200/25 blur-[120px]" />
          <div className="absolute -right-28 top-24 h-[36rem] w-[36rem] rounded-full bg-rose-200/25 blur-[130px]" />
        </>
      )}
    </div>
  )
}

function cardClass(isChief: boolean, extra = ""): string {
  return cn(
    "rounded-[2rem] border p-4 shadow-sm backdrop-blur-xl",
    isChief
      ? "border-white/10 bg-white/[0.045] text-slate-300"
      : "border-white/70 bg-white/50 text-stone-600",
    extra,
  )
}

function titleClass(isChief: boolean): string {
  return isChief ? "text-slate-100" : "text-stone-950"
}

function mutedClass(isChief: boolean): string {
  return isChief ? "text-slate-400" : "text-stone-500"
}

function subtleClass(isChief: boolean): string {
  return isChief ? "text-slate-500" : "text-stone-400"
}

function StatCard({
  label,
  value,
  helper,
  isChief,
}: {
  label: string
  value: number | string
  helper: string
  isChief: boolean
}) {
  return (
    <div
      className={cn(
        "rounded-[1.75rem] border p-4 shadow-sm backdrop-blur-xl",
        isChief ? "border-white/10 bg-white/[0.055]" : "border-white/70 bg-white/55",
      )}
    >
      <p className={cn("text-[11px] font-semibold uppercase tracking-[0.22em]", subtleClass(isChief))}>
        {label}
      </p>
      <p className={cn("mt-2 text-3xl font-semibold tracking-[-0.04em]", titleClass(isChief))}>
        {value}
      </p>
      <p className={cn("mt-1 text-xs leading-5", mutedClass(isChief))}>{helper}</p>
    </div>
  )
}

function FilterPill({
  active,
  children,
  onClick,
  isChief,
}: {
  active: boolean
  children: ReactNode
  onClick: () => void
  isChief: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-full px-3 py-1.5 text-xs font-semibold transition active:scale-[0.98]",
        active
          ? isChief
            ? "bg-teal-200 text-slate-950 shadow-sm"
            : "bg-stone-950 text-white shadow-sm"
          : isChief
            ? "border border-white/10 bg-white/[0.045] text-slate-400 hover:bg-white/[0.08] hover:text-slate-100"
            : "border border-stone-200 bg-white/60 text-stone-500 hover:bg-white hover:text-stone-950",
      )}
    >
      {children}
    </button>
  )
}

function EventCard({
  event,
  warning,
  previousEvent,
  isChief,
  onOpen,
}: {
  event: CalendarEvent
  warning?: string
  previousEvent?: CalendarEvent
  isChief: boolean
  onOpen: () => void
}) {
  const time = timeColumn(event)
  const meta = sourceMeta(event, isChief)
  const hasGoogleLink = Boolean(event.googleLink)

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(keyboardEvent) => {
        if (keyboardEvent.key === "Enter" || keyboardEvent.key === " ") {
          keyboardEvent.preventDefault()
          onOpen()
        }
      }}
      className={cn(
        "group relative cursor-pointer overflow-hidden rounded-[1.6rem] border p-4 shadow-sm backdrop-blur-xl transition hover:-translate-y-0.5 hover:shadow-md focus:outline-none focus:ring-2 focus:ring-teal-300/40",
        isChief
          ? "border-white/10 bg-white/[0.055] hover:border-teal-200/20 hover:bg-teal-200/[0.06] hover:shadow-black/25"
          : "border-white/70 bg-white/62 hover:bg-white/75 hover:shadow-stone-200/50",
      )}
    >
      <div
        className={cn(
          "pointer-events-none absolute inset-y-0 left-0 w-1 opacity-60",
          isChief
            ? "bg-gradient-to-b from-teal-200/35 via-teal-200/10 to-transparent"
            : "bg-gradient-to-b from-stone-900/20 via-stone-900/5 to-transparent",
        )}
      />

      <div className="flex gap-4">
        <div className={cn("w-16 shrink-0 pt-0.5 font-mono text-[11px] leading-5", mutedClass(isChief))}>
          <div className={cn("font-semibold tabular-nums", titleClass(isChief))}>{time.start}</div>
          {time.end ? <div className={cn("tabular-nums", subtleClass(isChief))}>{time.end}</div> : null}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <span className={`mt-0.5 h-2.5 w-2.5 rounded-full ${meta.dotClass}`} />
                <h3 className={cn("min-w-0 break-words text-base font-semibold leading-snug tracking-[-0.02em]", titleClass(isChief))}>
                  {event.title}
                </h3>
              </div>

              <div className="mt-2 flex flex-wrap items-center gap-2">
                <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${meta.badgeClass}`}>
                  {meta.label}
                </span>
                <span className={cn("text-[11px]", subtleClass(isChief))}>{meta.helper}</span>
              </div>
            </div>

            <ChevronRight className={cn("mt-1 h-4 w-4 shrink-0 transition group-hover:translate-x-0.5", isChief ? "text-slate-500 group-hover:text-teal-200" : "text-stone-300 group-hover:text-stone-500")} />
          </div>

          {event.location ? (
            <p className={cn("mt-3 flex items-center gap-1.5 text-sm leading-5", mutedClass(isChief))}>
              <MapPin className="h-3.5 w-3.5 shrink-0" />
              <span className="min-w-0 break-words">{event.location}</span>
            </p>
          ) : null}

          {event.syncError ? (
            <p className="mt-3 rounded-2xl border border-amber-300/20 bg-amber-300/10 px-3 py-2 text-xs leading-5 text-amber-200">
              Sync note: {event.syncError}
            </p>
          ) : null}

          {warning ? (
            <div className={cn("mt-3 rounded-2xl border p-3", isChief ? "border-amber-300/20 bg-amber-300/10" : "border-orange-200 bg-orange-50/85")}>
              <p className={cn("text-xs font-medium leading-5", isChief ? "text-amber-100" : "text-orange-800")}>{warning}</p>
              <button
                type="button"
                onClick={(clickEvent) => {
                  clickEvent.stopPropagation()
                  handoffCalendarActionToChat(event, "reschedule", warning)
                }}
                className={cn(
                  "mt-2 inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition",
                  isChief
                    ? "border-amber-300/20 bg-white/[0.05] text-amber-100 hover:bg-amber-300/10"
                    : "border-orange-200 bg-white/70 text-orange-700 hover:bg-white",
                )}
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
                onClick={(clickEvent) => clickEvent.stopPropagation()}
                target="_blank"
                rel="noreferrer"
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm transition",
                  isChief
                    ? "border-white/10 bg-white/[0.055] text-slate-300 hover:border-teal-200/25 hover:bg-teal-200/[0.08] hover:text-teal-100"
                    : "border-stone-200 bg-white/80 text-stone-700 hover:bg-white hover:text-stone-950",
                )}
              >
                <ExternalLink className="h-3.5 w-3.5" />
                Open Google
              </a>
            ) : null}

            {event.source === "local" ? (
              <button
                type="button"
                onClick={(clickEvent) => {
                  clickEvent.stopPropagation()
                  handoffCalendarActionToChat(event, "sync")
                }}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold transition",
                  isChief
                    ? "border-violet-300/20 bg-violet-300/[0.10] text-violet-100 hover:bg-violet-300/[0.15]"
                    : "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100",
                )}
              >
                <Sparkles className="h-3.5 w-3.5" />
                Ask Aliyya to sync
              </button>
            ) : null}

            {previousEvent ? (
              <span
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs",
                  isChief ? "border-white/10 bg-white/[0.045] text-slate-400" : "border-stone-200 bg-white/55 text-stone-500",
                )}
              >
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

function FreeTimeRow({ row, isChief }: { row: Extract<TimelineRow, { type: "free" }>; isChief: boolean }) {
  return (
    <div
      className={cn(
        "rounded-[1.4rem] border border-dashed px-4 py-3 text-sm backdrop-blur",
        isChief
          ? "border-white/10 bg-white/[0.035] text-slate-500"
          : "border-stone-200 bg-white/35 text-stone-500",
      )}
    >
      <div className="flex flex-wrap items-center gap-3">
        <span className={cn("font-mono text-xs tabular-nums", subtleClass(isChief))}>
          {formatTime(row.startAt)}–{formatTime(row.endAt)}
        </span>
        <span
          className={cn(
            "rounded-full border px-2.5 py-1 text-[11px] font-semibold",
            isChief ? "border-white/10 bg-white/[0.045] text-slate-400" : "border-white/70 bg-white/65 text-stone-500",
          )}
        >
          {durationLabel(row.minutes)} kosong
        </span>
      </div>
    </div>
  )
}

function EventDetailDrawer({
  event,
  isChief,
  onClose,
}: {
  event: CalendarEvent
  isChief: boolean
  onClose: () => void
}) {
  const meta = sourceMeta(event, isChief)
  const canOpenGoogle = Boolean(event.googleLink)

  return (
    <>
      <button
        type="button"
        aria-label="Close event detail"
        onClick={onClose}
        className="fixed inset-0 z-40 bg-black/20 backdrop-blur-[2px] lg:hidden"
      />

      <aside
        className={cn(
          "fixed bottom-4 right-4 top-4 z-50 flex w-[calc(100vw-2rem)] max-w-md flex-col overflow-hidden rounded-[2rem] border shadow-2xl backdrop-blur-2xl sm:w-[26rem]",
          isChief
            ? "border-white/10 bg-[#0b141d]/92 text-slate-100 shadow-black/45"
            : "border-white/75 bg-[#fbf8f1]/92 text-stone-950 shadow-stone-300/45",
        )}
      >
        <div
          className={cn(
            "flex items-start justify-between gap-4 border-b p-5",
            isChief ? "border-white/10" : "border-stone-200/70",
          )}
        >
          <div className="min-w-0">
            <p className={cn("text-[11px] font-semibold uppercase tracking-[0.24em]", subtleClass(isChief))}>
              Event detail
            </p>
            <h2 className={cn("mt-2 break-words text-2xl font-semibold tracking-[-0.045em]", titleClass(isChief))}>
              {event.title}
            </h2>
          </div>

          <button
            type="button"
            onClick={onClose}
            className={cn(
              "grid h-10 w-10 shrink-0 place-items-center rounded-full border transition",
              isChief
                ? "border-white/10 bg-white/[0.045] text-slate-300 hover:bg-white/[0.08] hover:text-white"
                : "border-stone-200 bg-white/70 text-stone-500 hover:bg-white hover:text-stone-950",
            )}
            aria-label="Close event detail"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto p-5 xl:[scrollbar-width:thin]">
          <div className="space-y-4">
            <div
              className={cn(
                "rounded-3xl border p-4",
                isChief ? "border-white/10 bg-white/[0.045]" : "border-white/70 bg-white/55",
              )}
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className={`h-2.5 w-2.5 rounded-full ${meta.dotClass}`} />
                <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.14em] ${meta.badgeClass}`}>
                  {meta.label}
                </span>
                <span className={cn("text-xs", mutedClass(isChief))}>{meta.helper}</span>
              </div>

              <dl className="mt-4 space-y-3 text-sm">
                <div>
                  <dt className={cn("text-xs font-semibold uppercase tracking-[0.18em]", subtleClass(isChief))}>
                    Date
                  </dt>
                  <dd className={cn("mt-1 font-medium", titleClass(isChief))}>{formatDate(event.date)}</dd>
                </div>

                <div>
                  <dt className={cn("text-xs font-semibold uppercase tracking-[0.18em]", subtleClass(isChief))}>
                    Time
                  </dt>
                  <dd className={cn("mt-1 font-medium", titleClass(isChief))}>{eventTimeLabel(event)}</dd>
                </div>

                <div>
                  <dt className={cn("text-xs font-semibold uppercase tracking-[0.18em]", subtleClass(isChief))}>
                    Location
                  </dt>
                  <dd className={cn("mt-1 font-medium", titleClass(isChief))}>{event.location || "No location set"}</dd>
                </div>

                <div>
                  <dt className={cn("text-xs font-semibold uppercase tracking-[0.18em]", subtleClass(isChief))}>
                    Source
                  </dt>
                  <dd className={cn("mt-1 font-medium", titleClass(isChief))}>
                    {event.source === "local"
                      ? "Aliyya local Calendar"
                      : event.source === "synced"
                        ? "Aliyya synced to Google Calendar"
                        : "Google Calendar"}
                  </dd>
                </div>
              </dl>
            </div>

            {event.syncError ? (
              <div className="rounded-3xl border border-amber-300/20 bg-amber-300/10 p-4 text-sm leading-6 text-amber-200">
                Sync note: {event.syncError}
              </div>
            ) : null}
          </div>
        </div>

        <div
          className={cn(
            "space-y-2 border-t p-5",
            isChief ? "border-white/10" : "border-stone-200/70",
          )}
        >
          {canOpenGoogle ? (
            <a
              href={event.googleLink || GOOGLE_CALENDAR_URL}
              target="_blank"
              rel="noreferrer"
              className={cn(
                "flex h-11 items-center justify-center gap-2 rounded-full border text-sm font-semibold transition",
                isChief
                  ? "border-white/10 bg-white/[0.055] text-slate-200 hover:border-teal-200/25 hover:bg-teal-200/[0.08] hover:text-teal-100"
                  : "border-stone-200 bg-white/80 text-stone-800 hover:bg-white hover:text-stone-950",
              )}
            >
              <ExternalLink className="h-4 w-4" />
              Open Google Calendar
            </a>
          ) : null}

          {event.source === "local" ? (
            <button
              type="button"
              onClick={() => handoffCalendarActionToChat(event, "sync")}
              className={cn(
                "flex h-11 w-full items-center justify-center gap-2 rounded-full border text-sm font-semibold transition",
                isChief
                  ? "border-violet-300/20 bg-violet-300/[0.10] text-violet-100 hover:bg-violet-300/[0.15]"
                  : "border-indigo-200 bg-indigo-50 text-indigo-700 hover:bg-indigo-100",
              )}
            >
              <Sparkles className="h-4 w-4" />
              Ask Aliyya to sync
            </button>
          ) : null}

          <button
            type="button"
            onClick={() => handoffCalendarActionToChat(event, "reschedule")}
            className={cn(
              "flex h-11 w-full items-center justify-center gap-2 rounded-full border text-sm font-semibold transition",
              isChief
                ? "border-white/10 bg-white/[0.045] text-slate-300 hover:bg-white/[0.08] hover:text-white"
                : "border-stone-200 bg-white/70 text-stone-700 hover:bg-white hover:text-stone-950",
            )}
          >
            <Bot className="h-4 w-4" />
            Ask Aliyya to reschedule
          </button>

          <button
            type="button"
            onClick={() => handoffCalendarActionToChat(event, "reminder")}
            className={cn(
              "flex h-11 w-full items-center justify-center gap-2 rounded-full border text-sm font-semibold transition",
              isChief
                ? "border-white/10 bg-white/[0.045] text-slate-300 hover:bg-white/[0.08] hover:text-white"
                : "border-stone-200 bg-white/70 text-stone-700 hover:bg-white hover:text-stone-950",
            )}
          >
            <Clock3 className="h-4 w-4" />
            Ask Aliyya to add reminder
          </button>
        </div>
      </aside>
    </>
  )
}

export default function CalendarPage() {
  const [snapshotKey, setSnapshotKey] = useState(LEGACY_CALENDAR_EVENTS_CACHE_KEY)
  const [events, setEvents] = useState<CalendarEvent[]>(() => readCalendarEventsSnapshot())
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [viewFilter, setViewFilter] = useState<ViewFilter>("upcoming")
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>("all")
  const [visualMode, setVisualMode] = useState<CalendarVisualMode>("life_companion")
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null)

  const isChief = visualMode === "chief_of_staff"
  const today = localDateKey()

  async function loadCalendarEvents() {
    setIsLoading(true)
    setError(null)

    try {
      const range = buildCalendarReadRange({
        // Backend Google Calendar read is capped at 31 days.
        // Keep this window safely below the cap so direct Google events stay visible.
        daysBefore: 3,
        daysAfter: 26,
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
    function syncVisualMode() {
      setVisualMode(readStoredCalendarVisualMode())
    }

    syncVisualMode()
    window.addEventListener("storage", syncVisualMode)
    window.addEventListener("focus", syncVisualMode)

    return () => {
      window.removeEventListener("storage", syncVisualMode)
      window.removeEventListener("focus", syncVisualMode)
    }
  }, [])

  useEffect(() => {
    if (typeof window === "undefined") return

    const eventId = new URLSearchParams(window.location.search).get("event")
    if (eventId) {
      setSelectedEventId(eventId)
    }
  }, [])

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
  const selectedEvent = selectedEventId
    ? events.find((event) => event.id === selectedEventId) || null
    : null

  function openEventDetails(event: CalendarEvent) {
    setSelectedEventId(event.id)

    if (typeof window !== "undefined") {
      const url = new URL(window.location.href)
      url.searchParams.set("event", event.id)
      window.history.replaceState(null, "", `${url.pathname}?${url.searchParams.toString()}`)
    }
  }

  function closeEventDetails() {
    setSelectedEventId(null)

    if (typeof window !== "undefined") {
      const url = new URL(window.location.href)
      url.searchParams.delete("event")
      window.history.replaceState(null, "", `${url.pathname}${url.search}`)
    }
  }

  const localCount = events.filter((event) => event.source === "local").length
  const syncedCount = events.filter((event) => event.source === "synced").length
  const googleCount = events.filter((event) => event.source === "google").length

  return (
    <main className={shellClass(isChief)}>
      <Background isChief={isChief} />

      <div className="relative mx-auto flex h-full w-full max-w-7xl flex-col gap-4">
        <header
          className={cn(
            "shrink-0 flex flex-col gap-3 rounded-[2rem] border p-4 shadow-sm backdrop-blur-xl sm:flex-row sm:items-start sm:justify-between sm:p-5",
            isChief ? "border-white/10 bg-white/[0.045]" : "border-white/70 bg-white/48",
          )}
        >
          <div>
            <p
              className={cn(
                "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.22em] shadow-sm",
                isChief
                  ? "border-teal-200/15 bg-teal-200/[0.06] text-teal-100"
                  : "border-stone-200 bg-white/60 text-stone-500",
              )}
            >
              <Sparkles className="h-3.5 w-3.5" />
              {isChief ? "Calm executive cockpit" : "Calendar command center"}
            </p>
            <h1 className={cn("mt-4 text-4xl font-semibold tracking-[-0.065em] sm:text-5xl", titleClass(isChief))}>
              Calendar
            </h1>
            <p className={cn("mt-3 max-w-2xl text-sm leading-6", mutedClass(isChief))}>
              {isChief
                ? "A focused operating deck for calendar risk, sync status, and next actions."
                : "A clean command deck for Aliyya events, Google Calendar sync, daily flow, and schedule gaps."}
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void loadCalendarEvents()}
              disabled={isLoading}
              className={cn(
                "inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-semibold shadow-sm backdrop-blur transition disabled:cursor-not-allowed disabled:opacity-60",
                isChief
                  ? "border-white/10 bg-white/[0.045] text-slate-300 hover:bg-white/[0.08] hover:text-white"
                  : "border-stone-200 bg-white/70 text-stone-700 hover:bg-white hover:text-stone-950",
              )}
            >
              {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCcw className="h-4 w-4" />}
              {isLoading ? "Refreshing" : "Refresh"}
            </button>

            <a
              href={GOOGLE_CALENDAR_URL}
              target="_blank"
              rel="noreferrer"
              className={cn(
                "inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-semibold shadow-sm backdrop-blur transition",
                isChief
                  ? "border-white/10 bg-white/[0.045] text-slate-300 hover:bg-white/[0.08] hover:text-white"
                  : "border-stone-200 bg-white/70 text-stone-700 hover:bg-white hover:text-stone-950",
              )}
            >
              <ArrowUpRight className="h-4 w-4" />
              Google Calendar
            </a>

            <a
              href="/chat-v2"
              className={cn(
                "inline-flex h-10 items-center justify-center rounded-full px-4 text-sm font-semibold shadow-sm transition",
                isChief ? "bg-teal-100 text-slate-950 hover:bg-teal-200" : "bg-stone-950 text-white hover:bg-stone-800",
              )}
            >
              Back to chat
            </a>
          </div>
        </header>

        <section className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[0.72fr_1.28fr]">
          <aside className="min-h-0 space-y-4 overflow-y-auto pr-1 xl:[scrollbar-width:thin]">
            <div className={cardClass(isChief)}>
              <div className="flex items-center gap-3">
                <span
                  className={cn(
                    "grid h-11 w-11 place-items-center rounded-2xl shadow-sm",
                    isChief ? "bg-teal-200 text-slate-950" : "bg-stone-950 text-white",
                  )}
                >
                  <Sunrise className="h-5 w-5" />
                </span>
                <div>
                  <p className={cn("text-[11px] font-semibold uppercase tracking-[0.22em]", subtleClass(isChief))}>
                    Today
                  </p>
                  <p className={cn("text-base font-semibold", titleClass(isChief))}>{formatDate(today)}</p>
                </div>
              </div>

              <div className="mt-4 grid grid-cols-3 gap-2">
                <StatCard label="Today" value={todaysEvents.length} helper="agenda" isChief={isChief} />
                <StatCard label="Synced" value={syncedCount} helper="Aliyya + Google" isChief={isChief} />
                <StatCard label="Local" value={localCount} helper="needs sync" isChief={isChief} />
              </div>
            </div>

            <div className={cardClass(isChief)}>
              <div className="mb-4 flex items-center gap-2">
                <Filter className={cn("h-4 w-4", subtleClass(isChief))} />
                <h2 className={cn("font-semibold", titleClass(isChief))}>View</h2>
              </div>

              <div className="flex flex-wrap gap-2">
                <FilterPill active={viewFilter === "today"} onClick={() => setViewFilter("today")} isChief={isChief}>
                  Today
                </FilterPill>
                <FilterPill active={viewFilter === "upcoming"} onClick={() => setViewFilter("upcoming")} isChief={isChief}>
                  Upcoming
                </FilterPill>
                <FilterPill active={viewFilter === "all"} onClick={() => setViewFilter("all")} isChief={isChief}>
                  All
                </FilterPill>
              </div>

              <div className="mt-4 flex flex-wrap gap-2">
                <FilterPill active={sourceFilter === "all"} onClick={() => setSourceFilter("all")} isChief={isChief}>
                  All source
                </FilterPill>
                <FilterPill active={sourceFilter === "aliyya"} onClick={() => setSourceFilter("aliyya")} isChief={isChief}>
                  Aliyya
                </FilterPill>
                <FilterPill active={sourceFilter === "google"} onClick={() => setSourceFilter("google")} isChief={isChief}>
                  Google
                </FilterPill>
              </div>
            </div>

            <div className={cardClass(isChief, "p-5")}>
              <div className="flex items-center gap-2">
                <Zap className={cn("h-4 w-4", subtleClass(isChief))} />
                <h2 className={cn("font-semibold", titleClass(isChief))}>Next focus</h2>
              </div>

              {nextEvent ? (
                <div
                  className={cn(
                    "mt-4 rounded-3xl border p-4",
                    isChief ? "border-white/10 bg-white/[0.045]" : "border-white/70 bg-white/55",
                  )}
                >
                  <p className={cn("text-xs font-semibold uppercase tracking-[0.18em]", subtleClass(isChief))}>
                    {formatCompactDate(nextEvent.date)} • {eventTimeLabel(nextEvent)}
                  </p>
                  <p className={cn("mt-2 text-lg font-semibold tracking-[-0.03em]", titleClass(isChief))}>
                    {nextEvent.title}
                  </p>
                  {nextEvent.location ? <p className={cn("mt-1 text-sm", mutedClass(isChief))}>{nextEvent.location}</p> : null}
                </div>
              ) : (
                <p className={cn("mt-4 text-sm leading-6", mutedClass(isChief))}>
                  No upcoming event in this view. Use chat to add a new agenda.
                </p>
              )}
            </div>

            <div className={cardClass(isChief, "p-5")}>
              <div className="flex items-center gap-2">
                <CheckCircle2 className={cn("h-4 w-4", subtleClass(isChief))} />
                <h2 className={cn("font-semibold", titleClass(isChief))}>Source health</h2>
              </div>
              <div className={cn("mt-4 space-y-2 text-sm", mutedClass(isChief))}>
                <div className="flex items-center justify-between">
                  <span>Google events</span>
                  <span className={cn("font-semibold", titleClass(isChief))}>{googleCount}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Synced Aliyya events</span>
                  <span className={cn("font-semibold", titleClass(isChief))}>{syncedCount}</span>
                </div>
                <div className="flex items-center justify-between">
                  <span>Local only</span>
                  <span className={cn("font-semibold", titleClass(isChief))}>{localCount}</span>
                </div>
              </div>
            </div>
          </aside>

          <section
            className={cn(
              "min-h-0 overflow-y-auto rounded-[2.25rem] border p-4 shadow-xl backdrop-blur-xl sm:p-5 xl:[scrollbar-width:thin]",
              isChief
                ? "border-white/10 bg-white/[0.045] shadow-black/25"
                : "border-white/70 bg-white/45 shadow-stone-200/50",
            )}
          >
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className={cn("text-[11px] font-semibold uppercase tracking-[0.24em]", subtleClass(isChief))}>
                  Agenda flow
                </p>
                <h2 className={cn("mt-1 text-2xl font-semibold tracking-[-0.045em]", titleClass(isChief))}>
                  {viewFilter === "today" ? "Today’s command deck" : viewFilter === "upcoming" ? "Upcoming timeline" : "All calendar events"}
                </h2>
                <p className={cn("mt-2 max-w-2xl text-sm leading-6", mutedClass(isChief))}>
                  Events are merged from Aliyya local memory and Google Calendar, then deduped for a cleaner planning view.
                </p>
              </div>

              <div
                className={cn(
                  "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold",
                  isChief ? "border-white/10 bg-white/[0.045] text-slate-400" : "border-stone-200 bg-white/60 text-stone-500",
                )}
              >
                <CalendarDays className="h-3.5 w-3.5" />
                {filteredEvents.length} shown
              </div>
            </div>

            {error ? (
              <div className="rounded-3xl border border-red-300/20 bg-red-300/10 p-4 text-sm leading-6 text-red-200">
                {error}
              </div>
            ) : null}

            {isLoading && groupedEvents.length === 0 ? (
              <div
                className={cn(
                  "grid min-h-[28rem] place-items-center rounded-[2rem] border border-dashed text-center",
                  isChief ? "border-white/10 bg-white/[0.035]" : "border-stone-200 bg-white/35",
                )}
              >
                <div>
                  <Loader2 className={cn("mx-auto h-7 w-7 animate-spin", subtleClass(isChief))} />
                  <p className={cn("mt-3 text-sm font-medium", mutedClass(isChief))}>Loading Calendar...</p>
                </div>
              </div>
            ) : !error && groupedEvents.length === 0 ? (
              <div
                className={cn(
                  "grid min-h-[28rem] place-items-center rounded-[2rem] border border-dashed p-8 text-center",
                  isChief ? "border-white/10 bg-white/[0.035]" : "border-stone-200 bg-white/35",
                )}
              >
                <div>
                  <Sparkles className={cn("mx-auto h-8 w-8", subtleClass(isChief))} />
                  <p className={cn("mt-4 text-lg font-semibold", titleClass(isChief))}>Belum ada agenda di view ini.</p>
                  <p className={cn("mt-2 max-w-md text-sm leading-6", mutedClass(isChief))}>
                    Coba sebutkan agenda di chat. Aliyya akan preview dulu sebelum memasukkannya ke Calendar.
                  </p>
                </div>
              </div>
            ) : (
              <div className="space-y-6">
                {isLoading ? (
                  <p
                    className={cn(
                      "rounded-full border px-3 py-1.5 text-xs font-medium",
                      isChief ? "border-white/10 bg-white/[0.045] text-slate-400" : "border-white/70 bg-white/55 text-stone-500",
                    )}
                  >
                    Refreshing latest schedule…
                  </p>
                ) : null}

                {groupedEvents.map((group) => (
                  <div key={group.date} className="space-y-3">
                    <div className="flex items-center justify-between gap-3 px-1">
                      <h3 className={cn("text-xs font-semibold uppercase tracking-[0.22em]", subtleClass(isChief))}>
                        {formatDate(group.date)}
                      </h3>
                      <span className={cn("text-xs", subtleClass(isChief))}>{group.events.length} agenda</span>
                    </div>

                    <div className="space-y-3">
                      {buildTimelineRows(group.events).map((row) => {
                        if (row.type === "free") {
                          return <FreeTimeRow key={row.id} row={row} isChief={isChief} />
                        }

                        return (
                          <EventCard
                            key={row.event.id}
                            event={row.event}
                            warning={row.warning}
                            previousEvent={row.previousEvent}
                            isChief={isChief}
                            onOpen={() => openEventDetails(row.event)}
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

      {selectedEvent ? (
        <EventDetailDrawer
          event={selectedEvent}
          isChief={isChief}
          onClose={closeEventDetails}
        />
      ) : null}
    </main>
  )
}
