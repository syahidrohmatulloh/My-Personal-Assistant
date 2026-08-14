import {
  getTodayBriefing,
  getTodaysJournal,
  listGoals,
  listMemories,
  listPeople,
} from "@/lib/api";
import {
  loadTodayWorkspaceAgenda,
  loadUpcomingWorkspaceReminders,
} from "./load-live-context";
import type { WorkspaceContext } from "./types";

type LoadWorkspaceContextOptions = {
  assistantName?: string | null;
};

type SourceResult = PromiseSettledResult<unknown>;

function sourceHealthStatus(
  result: SourceResult,
  hasItems: boolean,
): "live" | "empty" | "failed" {
  if (result.status === "rejected") return "failed";
  return hasItems ? "live" : "empty";
}

function sourceHealthDetail(
  result: SourceResult,
  liveDetail: string,
  emptyDetail: string,
): string {
  if (result.status === "rejected") return "Source failed to load";
  return liveDetail || emptyDetail;
}

function settledValue<T>(
  result: PromiseSettledResult<T>,
  fallback: T,
): T {
  return result.status === "fulfilled" ? result.value : fallback;
}

function compactString(value: unknown): string | null {
  const text = String(value ?? "").replace(/\s+/g, " ").trim();
  return text || null;
}

export async function loadAssistantWorkspaceContext(
  options: LoadWorkspaceContextOptions = {},
): Promise<WorkspaceContext> {
  const [
    briefingResult,
    journalResult,
    activeGoalsResult,
    pausedGoalsResult,
    memoriesResult,
    peopleResult,
    agendaResult,
    remindersResult,
  ] = await Promise.allSettled([
    getTodayBriefing(),
    getTodaysJournal(),
    listGoals("active"),
    listGoals("paused"),
    listMemories(),
    listPeople(),
    loadTodayWorkspaceAgenda(),
    loadUpcomingWorkspaceReminders(),
  ]);

  const briefing = settledValue(briefingResult, null);
  const journal = settledValue(journalResult, { entry: null });
  const activeGoals = settledValue(activeGoalsResult, []);
  const pausedGoals = settledValue(pausedGoalsResult, []);
  const memories = settledValue(memoriesResult, []);
  const people = settledValue(peopleResult, []);
  const todayAgenda = settledValue(agendaResult, []);
  const upcomingReminders = settledValue(remindersResult, []);

  const rejectedCount = [
    briefingResult,
    journalResult,
    activeGoalsResult,
    pausedGoalsResult,
    memoriesResult,
    peopleResult,
    agendaResult,
    remindersResult,
  ].filter((result) => result.status === "rejected").length;

  const normalizedActiveGoals = activeGoals.map((goal) => ({
    id: goal.id,
    title: goal.title,
    status: goal.status,
  }));
  const normalizedPausedGoals = pausedGoals.map((goal) => ({
    id: goal.id,
    title: goal.title,
    status: goal.status,
  }));
  const normalizedPeople = people.map((person) => ({
    id: person.id,
    name: person.name,
    relationship: person.relationship ?? null,
  }));
  const normalizedMemories = memories.slice(0, 5).map((memory) => ({
    id: memory.id,
    content: compactString(memory.content) ?? "Memory",
    kind: memory.kind,
    createdAt: memory.created_at,
  }));
  const nowIso = new Date().toISOString();

  return {
    status: rejectedCount >= 8 ? "error" : "ready",
    briefingContent: briefing?.content ?? null,
    briefingOpenedAt: briefing?.opened_at ?? null,
    briefingConversationId: briefing?.conversation_id ?? null,
    journaledToday: Boolean(journal?.entry),
    activeGoals: normalizedActiveGoals,
    pausedGoals: normalizedPausedGoals,
    people: normalizedPeople,
    recentMemories: normalizedMemories,
    todayAgenda,
    upcomingReminders,
    agendaStatus: agendaResult.status === "fulfilled" ? "ready" : "error",
    remindersStatus: remindersResult.status === "fulfilled" ? "ready" : "error",
    sourceHealth: [
      {
        id: "agenda",
        label: "Calendar",
        status: sourceHealthStatus(agendaResult, todayAgenda.length > 0),
        detail: sourceHealthDetail(
          agendaResult,
          `${todayAgenda.length} item${todayAgenda.length === 1 ? "" : "s"} today`,
          "No agenda surfaced today",
        ),
        updatedAt: nowIso,
      },
      {
        id: "reminders",
        label: "Reminders",
        status: sourceHealthStatus(remindersResult, upcomingReminders.length > 0),
        detail: sourceHealthDetail(
          remindersResult,
          `${upcomingReminders.length} upcoming`,
          "No reminders surfaced",
        ),
        updatedAt: nowIso,
      },
      {
        id: "brief",
        label: "Brief",
        status: sourceHealthStatus(briefingResult, Boolean(briefing?.content)),
        detail: sourceHealthDetail(
          briefingResult,
          "Daily brief available",
          "No daily brief yet",
        ),
        updatedAt: nowIso,
      },
      {
        id: "journal",
        label: "Journal",
        status: sourceHealthStatus(journalResult, Boolean(journal?.entry)),
        detail: sourceHealthDetail(
          journalResult,
          "Journaled today",
          "No journal entry today",
        ),
        updatedAt: nowIso,
      },
      {
        id: "goals",
        label: "Goals",
        status: sourceHealthStatus(
          activeGoalsResult.status === "rejected" ? activeGoalsResult : pausedGoalsResult,
          normalizedActiveGoals.length + normalizedPausedGoals.length > 0,
        ),
        detail:
          activeGoalsResult.status === "rejected" || pausedGoalsResult.status === "rejected"
            ? "Source failed to load"
            : `${normalizedActiveGoals.length} active · ${normalizedPausedGoals.length} paused`,
        updatedAt: nowIso,
      },
      {
        id: "memories",
        label: "Memory",
        status: sourceHealthStatus(memoriesResult, normalizedMemories.length > 0),
        detail: sourceHealthDetail(
          memoriesResult,
          `${normalizedMemories.length} surfaced`,
          "No memories surfaced",
        ),
        updatedAt: nowIso,
      },
      {
        id: "people",
        label: "People",
        status: sourceHealthStatus(peopleResult, normalizedPeople.length > 0),
        detail: sourceHealthDetail(
          peopleResult,
          `${normalizedPeople.length} people`,
          "No people surfaced",
        ),
        updatedAt: nowIso,
      },
    ],
    assistantName: options.assistantName ?? null,
  };
}
