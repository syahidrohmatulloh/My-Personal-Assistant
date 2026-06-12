import {
  buildCalendarReadRange,
  loadMergedCalendarEvents,
} from "@/lib/calendar-snapshot";
import type {
  WorkspaceAgendaItem,
  WorkspaceReminder,
} from "./types";

function localDateKey(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export async function loadTodayWorkspaceAgenda(): Promise<WorkspaceAgendaItem[]> {
  const range = buildCalendarReadRange({
    daysBefore: 0,
    daysAfter: 1,
  })
  const events = await loadMergedCalendarEvents(range)
  const today = localDateKey()

  return events
    .filter((event) => event.date === today)
    .slice(0, 5)
    .map((event) => ({
      id: event.id,
      title: event.title,
      date: event.date,
      startAt: event.startAt,
      endAt: event.endAt,
      allDay: event.allDay,
      status: event.status,
      source: event.source,
      googleEventId: event.googleEventId,
      location: event.location ?? null,
    }))
}

export async function loadUpcomingWorkspaceReminders(): Promise<WorkspaceReminder[]> {
  const response = await fetch("/api/memory-review/upcoming-reminders?limit=5", {
    method: "GET",
    credentials: "include",
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Workspace reminders request failed: ${response.status}`);
  }

  const payload = await response.json();
  const items = Array.isArray(payload?.items) ? payload.items : [];

  return items
    .map((item: Record<string, unknown>) => ({
      id: typeof item.id === "string" ? item.id : undefined,
      title: typeof item.title === "string" ? item.title : "Reminder",
      message: typeof item.message === "string" ? item.message : null,
      dueAt: typeof item.due_at === "string" ? item.due_at : undefined,
      status: typeof item.status === "string" ? item.status : undefined,
    }))
    .filter((item: WorkspaceReminder) => Boolean(item.dueAt))
    .slice(0, 5);
}
