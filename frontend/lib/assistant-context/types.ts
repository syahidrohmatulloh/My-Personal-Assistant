import type { AssistantMode } from "@/lib/api";

export type WorkspaceCardId =
  | "proactive_daily_brief"
  | "proactive_next_actions"
  | "memory_intelligence"
  | "relationship_radar"
  | "project_tracker"
  | "gentle_checkin"
  | "personal_ideas"
  | "continuity_signal"
  | "soft_briefing"
  | "people_who_matter"
  | "recent_memories"
  | "today_agenda"
  | "upcoming_reminders"
  | "today_brief"
  | "priority_queue"
  | "briefing_topics"
  | "risks_blockers";

export type WorkspaceGoal = {
  id?: string;
  title?: string;
  status?: string;
};

export type WorkspacePerson = {
  id?: string;
  name?: string;
  relationship?: string | null;
};

export type WorkspaceMemory = {
  id?: string;
  content?: string;
  kind?: string;
  createdAt?: string;
};

export type WorkspaceAgendaItem = {
  id?: string;
  title?: string;
  date?: string;
  startAt?: string | null;
  endAt?: string | null;
  allDay?: boolean;
  status?: string;
  source?: "local" | "synced" | "google";
  googleEventId?: string | null;
  googleLink?: string | null;
  location?: string | null;
};

export type WorkspaceReminder = {
  id?: string;
  title?: string;
  message?: string | null;
  dueAt?: string;
  status?: string;
};

export type WorkspaceContext = {
  status: "loading" | "ready" | "error";
  briefingContent?: string | null;
  briefingOpenedAt?: string | null;
  briefingConversationId?: string | null;
  journaledToday?: boolean;
  activeGoals?: WorkspaceGoal[];
  pausedGoals?: WorkspaceGoal[];
  people?: WorkspacePerson[];
  recentMemories?: WorkspaceMemory[];
  todayAgenda?: WorkspaceAgendaItem[];
  upcomingReminders?: WorkspaceReminder[];
  agendaStatus?: "loading" | "ready" | "error";
  remindersStatus?: "loading" | "ready" | "error";
  assistantName?: string | null;
};

export type WorkspaceModeKey = "life" | "chief";

export function modeKey(mode: AssistantMode): WorkspaceModeKey {
  return mode === "chief_of_staff" ? "chief" : "life";
}
