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
  google_calendar_event_id?: string | null
  google_calendar_event_link?: string | null
  calendar_sync_error?: string | null
}

export type CalendarEvent = {
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

export const LEGACY_CALENDAR_EVENTS_CACHE_KEY = "app:calendar-events-cache:v1"
export const CALENDAR_SNAPSHOT_AREA = "calendar"

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
    status,
    googleLink: item.google_calendar_event_link || null,
    syncError: item.calendar_sync_error || null,
  }
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
    (item.status === "confirmed_local" || item.status === "synced_google")
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

  return snapshot?.data.sort(sortCalendarEvents) ?? []
}

export function writeCalendarEventsSnapshot(
  events: CalendarEvent[],
  key = LEGACY_CALENDAR_EVENTS_CACHE_KEY,
) {
  writeSnapshot(key, events)
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
