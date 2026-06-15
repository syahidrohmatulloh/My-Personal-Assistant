import { createClient } from "@/lib/supabase/client"
import { readSnapshot, SNAPSHOT_MAX_AGE_MS, userScopedSnapshotKey, writeSnapshot } from "@/lib/snapshot-cache"

export type RawCalendarItem = {
  id?: string
  title?: string
  content?: string
  structured_value?: string
  due_date?: string
  calendar_candidate?: boolean
  calendar_event_status?: string | null
  calendar_event_title?: string | null
  calendar_event_date?: string | null
  calendar_event_start_at?: string | null
  calendar_event_end_at?: string | null
  calendar_event_all_day?: boolean | null
  calendar_event_location?: string | null
  google_calendar_event_id?: string | null
  google_calendar_event_link?: string | null
  calendar_sync_error?: string | null
}

export type RawGoogleCalendarEvent = {
  id?: string
  title?: string
  event_date?: string
  start_at?: string | null
  end_at?: string | null
  all_day?: boolean
  location?: string | null
  html_link?: string | null
  status?: string | null
  source?: string
}

export type CalendarEvent = {
  id: string
  title: string
  date: string
  startAt: string | null
  endAt: string | null
  allDay: boolean
  location: string | null
  status: "confirmed_local" | "synced_google" | "google"
  source: "local" | "synced" | "google"
  googleEventId: string | null
  googleLink: string | null
  syncError: string | null
}

export type CalendarReadRange = {
  start: string
  end: string
  timeZone: string
}

export const LEGACY_CALENDAR_EVENTS_CACHE_KEY = "app:calendar-events-cache:v1"
export const CALENDAR_SNAPSHOT_AREA = "calendar"
export const CALENDAR_SNAPSHOT_INVALIDATED_EVENT = "app:calendar-snapshot-invalidated"

export function calendarSnapshotKeyForUser(userId: string): string {
  return userScopedSnapshotKey({
    userId,
    area: CALENDAR_SNAPSHOT_AREA,
  })
}

export function normalizeCalendarTitle(item: RawCalendarItem): string {
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

export function normalizeCalendarLocation(item: RawCalendarItem): string | null {
  const raw = String(item.calendar_event_location || "").replace(/\s+/g, " ").trim()
  return raw ? raw.slice(0, 180) : null
}

export function normalizeCalendarEvent(item: RawCalendarItem): CalendarEvent | null {
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
    location: normalizeCalendarLocation(item),
    status,
    source: status === "synced_google" ? "synced" : "local",
    googleEventId: item.google_calendar_event_id || null,
    googleLink: item.google_calendar_event_link || null,
    syncError: item.calendar_sync_error || null,
  }
}

export function normalizeGoogleCalendarEvent(
  item: RawGoogleCalendarEvent,
): CalendarEvent | null {
  const googleEventId = String(item.id || "").trim()
  const date = String(item.event_date || "").trim()

  if (!googleEventId || !date) {
    return null
  }

  const title = String(item.title || "Untitled event")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 250) || "Untitled event"

  const location = String(item.location || "")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 180) || null

  return {
    id: `google:${googleEventId}`,
    title,
    date,
    startAt: item.start_at || null,
    endAt: item.end_at || null,
    allDay: Boolean(item.all_day),
    location,
    status: "google",
    source: "google",
    googleEventId,
    googleLink: item.html_link || null,
    syncError: null,
  }
}

function canonicalEventTime(value: string | null): string {
  if (!value) {
    return ""
  }

  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime()) ? value : parsed.toISOString()
}

function calendarEventFingerprint(event: CalendarEvent): string {
  const title = event.title
    .toLocaleLowerCase()
    .replace(/[^a-z0-9]+/gi, " ")
    .replace(/\s+/g, " ")
    .trim()

  return [
    title,
    event.date,
    event.allDay ? "all-day" : canonicalEventTime(event.startAt),
    event.allDay ? "" : canonicalEventTime(event.endAt),
  ].join("|")
}


function calendarEventDisplayPriority(event: CalendarEvent): number {
  if (event.source === "synced" && event.googleEventId) return 50
  if (event.source === "google" && event.googleEventId) return 40
  if (event.source === "synced") return 30
  if (event.source === "local") return 10
  return 0
}

function pickDisplayCalendarEvent(
  current: CalendarEvent,
  candidate: CalendarEvent,
): CalendarEvent {
  const currentPriority = calendarEventDisplayPriority(current)
  const candidatePriority = calendarEventDisplayPriority(candidate)

  if (candidatePriority > currentPriority) {
    return candidate
  }

  if (candidatePriority < currentPriority) {
    return current
  }

  if (!current.location && candidate.location) {
    return candidate
  }

  if (!current.googleLink && candidate.googleLink) {
    return candidate
  }

  if (!current.googleEventId && candidate.googleEventId) {
    return candidate
  }

  return current
}

export function dedupeCalendarEventsForDisplay(
  events: CalendarEvent[],
): CalendarEvent[] {
  const byFingerprint = new Map<string, CalendarEvent>()

  for (const event of events) {
    const fingerprint = calendarEventFingerprint(event)
    const existing = byFingerprint.get(fingerprint)

    byFingerprint.set(
      fingerprint,
      existing ? pickDisplayCalendarEvent(existing, event) : event,
    )
  }

  return Array.from(byFingerprint.values())
}


export function mergeCalendarEvents(
  localEvents: CalendarEvent[],
  googleEvents: CalendarEvent[],
): CalendarEvent[] {
  const merged = [...localEvents]

  const localIndexByGoogleId = new Map<string, number>()
  const localIndexByFingerprint = new Map<string, number>()

  merged.forEach((event, index) => {
    if (event.googleEventId) {
      localIndexByGoogleId.set(event.googleEventId, index)
    }

    const fingerprint = calendarEventFingerprint(event)
    if (!localIndexByFingerprint.has(fingerprint)) {
      localIndexByFingerprint.set(fingerprint, index)
    }
  })

  for (const googleEvent of googleEvents) {
    const googleEventId = googleEvent.googleEventId
    const idMatch =
      googleEventId ? localIndexByGoogleId.get(googleEventId) : undefined

    if (idMatch !== undefined) {
      const localEvent = merged[idMatch]

      merged[idMatch] = {
        ...localEvent,
        title: googleEvent.title,
        date: googleEvent.date,
        startAt: googleEvent.startAt,
        endAt: googleEvent.endAt,
        allDay: googleEvent.allDay,
        location: googleEvent.location ?? localEvent.location,
        status: "synced_google",
        source: "synced",
        googleEventId,
        googleLink: googleEvent.googleLink ?? localEvent.googleLink,
      }
      continue
    }

    const fingerprint = calendarEventFingerprint(googleEvent)
    const fingerprintMatch = localIndexByFingerprint.get(fingerprint)

    if (fingerprintMatch !== undefined) {
      merged[fingerprintMatch] = googleEvent
      continue
    }

    merged.push(googleEvent)
  }

  return dedupeCalendarEventsForDisplay(merged).sort(sortCalendarEvents)
}

export function buildCalendarReadRange({
  daysBefore = 7,
  daysAfter = 24,
  now = new Date(),
}: {
  daysBefore?: number
  daysAfter?: number
  now?: Date
} = {}): CalendarReadRange {
  const start = new Date(now)
  start.setHours(0, 0, 0, 0)
  start.setDate(start.getDate() - daysBefore)

  const end = new Date(now)
  end.setHours(0, 0, 0, 0)
  end.setDate(end.getDate() + daysAfter)

  const timeZone =
    Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC"

  return {
    start: start.toISOString(),
    end: end.toISOString(),
    timeZone,
  }
}

export async function loadMergedCalendarEvents(
  range: CalendarReadRange,
): Promise<CalendarEvent[]> {
  const googleParams = new URLSearchParams({
    start: range.start,
    end: range.end,
    time_zone: range.timeZone,
  })

  const localRequest = fetch("/api/memory-review/calendar-candidates", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  })

  const googleRequest = fetch(
    `/api/calendar/oauth/events?${googleParams.toString()}`,
    {
      method: "GET",
      credentials: "include",
      cache: "no-store",
    },
  ).catch(() => null)

  const [localResponse, googleResponse] = await Promise.all([
    localRequest,
    googleRequest,
  ])

  if (!localResponse.ok) {
    throw new Error(`Calendar request failed: ${localResponse.status}`)
  }

  const localPayload = await localResponse.json()
  const localItems = Array.isArray(localPayload?.items)
    ? localPayload.items
    : []

  const localEvents = localItems
    .map((item: RawCalendarItem) => normalizeCalendarEvent(item))
    .filter(Boolean) as CalendarEvent[]

  let googleEvents: CalendarEvent[] = []

  if (googleResponse?.ok) {
    const googlePayload = await googleResponse.json()
    const googleItems = Array.isArray(googlePayload?.events)
      ? googlePayload.events
      : []

    googleEvents = googleItems
      .map((item: RawGoogleCalendarEvent) =>
        normalizeGoogleCalendarEvent(item),
      )
      .filter(Boolean) as CalendarEvent[]
  }

  return mergeCalendarEvents(localEvents, googleEvents)
}

export function sortCalendarEvents(a: CalendarEvent, b: CalendarEvent): number {
  const aKey = `${a.date} ${a.startAt || "99:99"} ${a.title}`
  const bKey = `${b.date} ${b.startAt || "99:99"} ${b.title}`
  return aKey.localeCompare(bKey)
}

export function isCalendarEvent(value: unknown): value is CalendarEvent {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return false
  }

  const item = value as Partial<CalendarEvent>

  return (
    typeof item.id === "string" &&
    typeof item.title === "string" &&
    typeof item.date === "string" &&
    (item.location === undefined || item.location === null || typeof item.location === "string") &&
    (
      item.status === "confirmed_local" ||
      item.status === "synced_google" ||
      item.status === "google"
    ) &&
    (
      item.source === undefined ||
      item.source === "local" ||
      item.source === "synced" ||
      item.source === "google"
    ) &&
    (
      item.googleEventId === undefined ||
      item.googleEventId === null ||
      typeof item.googleEventId === "string"
    )
  )
}

export function isCalendarEventArray(value: unknown): value is CalendarEvent[] {
  return Array.isArray(value) && value.every(isCalendarEvent)
}

export function readCalendarEventsSnapshot(
  key = LEGACY_CALENDAR_EVENTS_CACHE_KEY,
): CalendarEvent[] {
  const snapshot = readSnapshot<CalendarEvent[]>(
    key,
    [],
    isCalendarEventArray,
    { maxAgeMs: SNAPSHOT_MAX_AGE_MS.calendar },
  )

  return (
    snapshot?.data.map((event) => ({
      ...event,
      source:
        event.source ||
        (event.status === "synced_google" ? "synced" : "local"),
      googleEventId: event.googleEventId ?? null,
    })).sort(sortCalendarEvents) ?? []
  )
}

export function writeCalendarEventsSnapshot(
  events: CalendarEvent[],
  key = LEGACY_CALENDAR_EVENTS_CACHE_KEY,
) {
  writeSnapshot(key, events)
}

export function dispatchCalendarSnapshotInvalidated() {
  if (typeof window === "undefined") {
    return
  }

  window.dispatchEvent(new CustomEvent(CALENDAR_SNAPSHOT_INVALIDATED_EVENT))
}

export function clearCalendarEventsSnapshot(key = LEGACY_CALENDAR_EVENTS_CACHE_KEY) {
  if (typeof window === "undefined") {
    return
  }

  try {
    window.localStorage.removeItem(key)
  } catch {
    // Ignore storage failures.
  }

  dispatchCalendarSnapshotInvalidated()
}

export async function clearCalendarEventsSnapshotsForCurrentUser() {
  clearCalendarEventsSnapshot(LEGACY_CALENDAR_EVENTS_CACHE_KEY)

  if (typeof window === "undefined") {
    return
  }

  try {
    const supabase = createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()

    const userId = session?.user?.id
    if (!userId) {
      return
    }

    clearCalendarEventsSnapshot(calendarSnapshotKeyForUser(userId))
  } catch {
    // Ignore auth/storage failures. The Calendar page will fetch fresh if needed.
  }
}
