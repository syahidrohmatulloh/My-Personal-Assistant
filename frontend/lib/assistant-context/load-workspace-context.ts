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

  return {
    status: rejectedCount >= 8 ? "error" : "ready",
    briefingContent: briefing?.content ?? null,
    briefingOpenedAt: briefing?.opened_at ?? null,
    briefingConversationId: briefing?.conversation_id ?? null,
    journaledToday: Boolean(journal?.entry),
    activeGoals: activeGoals.map((goal) => ({
      id: goal.id,
      title: goal.title,
      status: goal.status,
    })),
    pausedGoals: pausedGoals.map((goal) => ({
      id: goal.id,
      title: goal.title,
      status: goal.status,
    })),
    people: people.map((person) => ({
      id: person.id,
      name: person.name,
      relationship: person.relationship ?? null,
    })),
    recentMemories: memories.slice(0, 5).map((memory) => ({
      id: memory.id,
      content: compactString(memory.content) ?? "Memory",
      kind: memory.kind,
      createdAt: memory.created_at,
    })),
    todayAgenda,
    upcomingReminders,
    agendaStatus: agendaResult.status === "fulfilled" ? "ready" : "error",
    remindersStatus: remindersResult.status === "fulfilled" ? "ready" : "error",
    assistantName: options.assistantName ?? null,
  };
}
