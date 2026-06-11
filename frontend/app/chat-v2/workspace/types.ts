import type { AssistantMode } from "@/lib/api";

export type WorkspaceCardId =
  | "gentle_checkin"
  | "personal_ideas"
  | "continuity_signal"
  | "soft_briefing"
  | "people_who_matter"
  | "recent_memories"
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
  assistantName?: string | null;
};

export type WorkspaceModeKey = "life" | "chief";

export function modeKey(mode: AssistantMode): WorkspaceModeKey {
  return mode === "chief_of_staff" ? "chief" : "life";
}
