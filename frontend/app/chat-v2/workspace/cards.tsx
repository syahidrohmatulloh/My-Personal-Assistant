import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
  Brain,
  CalendarDays,
  CheckCircle2,
  CircleDot,
  Compass,
  Heart,
  Lightbulb,
  Newspaper,
  NotebookPen,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";
import type { AssistantMode } from "@/lib/api";
import type { WorkspaceCardId, WorkspaceContext } from "./types";

export type WorkspaceCardDefinition = {
  id: WorkspaceCardId;
  title: string;
  icon: LucideIcon;
  modes: AssistantMode[];
  defaultVisible: boolean;
  render: (context: WorkspaceContext) => ReactNode;
};

const LIFE: AssistantMode[] = ["life_companion"];
const CHIEF: AssistantMode[] = ["chief_of_staff"];
const BOTH: AssistantMode[] = ["life_companion", "chief_of_staff"];

function truncateText(value: string | null | undefined, maxLength = 140): string | null {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return null;
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trim()}…`;
}

function goalTitles(goals: WorkspaceContext["activeGoals"]): string[] {
  return (goals || [])
    .map((goal) => String(goal.title || "").trim())
    .filter(Boolean)
    .slice(0, 3);
}

function joinNaturally(items: string[]): string {
  if (items.length <= 1) return items.join("");
  if (items.length === 2) return `${items[0]} and ${items[1]}`;
  return `${items.slice(0, -1).join(", ")}, and ${items[items.length - 1]}`;
}

function formatClock(value: string | null | undefined): string | null {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  return new Intl.DateTimeFormat("id-ID", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

function formatReminderDue(value: string | null | undefined): string {
  if (!value) return "Time unavailable";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Time unavailable";

  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();

  if (sameDay) {
    return `Today, ${formatClock(value) || ""}`.replace(/, $/, "");
  }

  return new Intl.DateTimeFormat("id-ID", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(date);
}

export const WORKSPACE_CARDS: WorkspaceCardDefinition[] = [
  {
    id: "gentle_checkin",
    title: "Gentle check-in",
    icon: Heart,
    modes: LIFE,
    defaultVisible: true,
    render: (context) =>
      context.status === "loading" ? (
        <p>Preparing your personal context…</p>
      ) : context.journaledToday ? (
        <p>You have already opened today’s reflection. This space can continue from that thread gently.</p>
      ) : (
        <p>No journal entry yet today. This can become a calm place to close the loop or process what is on your mind.</p>
      ),
  },
  {
    id: "personal_ideas",
    title: "Personal ideas",
    icon: Lightbulb,
    modes: LIFE,
    defaultVisible: true,
    render: (context) => {
      const goals = goalTitles(context.activeGoals);
      return goals.length > 0 ? (
        <ul>
          {goals.map((goal) => (
            <li key={goal}>{goal}</li>
          ))}
        </ul>
      ) : (
        <p>Ideas, personal plans, and things to revisit will sit here without crowding the main chat.</p>
      );
    },
  },
  {
    id: "continuity_signal",
    title: "Continuity signal",
    icon: Brain,
    modes: LIFE,
    defaultVisible: true,
    render: (context) => {
      const name = String(context.assistantName || "").trim() || "Your assistant";
      const signals: string[] = [];
      if (context.journaledToday) signals.push("today’s reflection");
      const goalCount = (context.activeGoals || []).length;
      if (goalCount > 0) signals.push(`${goalCount} active goal${goalCount === 1 ? "" : "s"}`);
      const peopleCount = (context.people || []).length;
      if (peopleCount > 0) signals.push(`${peopleCount} ${peopleCount === 1 ? "person" : "people"} who matter`);

      return signals.length > 0 ? (
        <p>
          {name} is keeping {joinNaturally(signals)} in reach, so this conversation can pick up where life actually is.
        </p>
      ) : (
        <p>{name} keeps your journal, goals, and recent threads in reach while the chat area stays quiet.</p>
      );
    },
  },
  {
    id: "soft_briefing",
    title: "Soft briefing",
    icon: Compass,
    modes: LIFE,
    defaultVisible: true,
    render: (context) => {
      const briefingSnippet = truncateText(context.briefingContent, 150);
      return briefingSnippet ? (
        <p>{briefingSnippet}</p>
      ) : (
        <p>Later this can become a personal digest: family, ideas, health rhythm, or any topic you ask the assistant to track.</p>
      );
    },
  },
  {
    id: "people_who_matter",
    title: "People who matter",
    icon: Users,
    modes: LIFE,
    defaultVisible: false,
    render: (context) => {
      const people = (context.people || []).slice(0, 4);
      if (context.status === "loading") {
        return <p>Gathering the people closest to you…</p>;
      }
      return people.length > 0 ? (
        <ul>
          {people.map((person, index) => (
            <li key={person.id || person.name || index}>
              {person.name}
              {person.relationship ? ` — ${person.relationship}` : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p>People you add in the People space will appear here, close to the conversation.</p>
      );
    },
  },
  {
    id: "recent_memories",
    title: "Recent memories",
    icon: NotebookPen,
    modes: BOTH,
    defaultVisible: false,
    render: (context) => {
      const memories = (context.recentMemories || []).slice(0, 3);
      if (context.status === "loading") {
        return <p>Collecting the latest saved memories…</p>;
      }
      return memories.length > 0 ? (
        <ul>
          {memories.map((memory, index) => (
            <li key={memory.id || index}>{truncateText(memory.content, 90)}</li>
          ))}
        </ul>
      ) : (
        <p>The latest things saved to memory will appear here as short notes.</p>
      );
    },
  },
  {
    id: "today_agenda",
    title: "Today's agenda",
    icon: CalendarDays,
    modes: BOTH,
    defaultVisible: true,
    render: (context) => {
      if (context.status === "loading" || context.agendaStatus === "loading") {
        return <p>Bringing today’s schedule into focus…</p>;
      }

      if (context.agendaStatus === "error") {
        return <p>Today’s agenda could not be refreshed. The rest of your workspace is still available.</p>;
      }

      const agenda = (context.todayAgenda || []).slice(0, 4);

      return agenda.length > 0 ? (
        <ul>
          {agenda.map((event, index) => {
            const time = event.allDay
              ? "All day"
              : formatClock(event.startAt) || "Time pending";

            return (
              <li key={event.id || `${event.title}-${index}`}>
                <span className="font-medium">{time}</span>
                {event.title ? ` — ${event.title}` : ""}
                {event.location ? (
                  <span className="block truncate pl-0.5 text-xs opacity-70">{event.location}</span>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : (
        <p>No confirmed events are scheduled here for today. You can ask the assistant to add or organize one.</p>
      );
    },
  },
  {
    id: "upcoming_reminders",
    title: "Upcoming reminders",
    icon: AlarmClock,
    modes: BOTH,
    defaultVisible: true,
    render: (context) => {
      if (context.status === "loading" || context.remindersStatus === "loading") {
        return <p>Checking what you asked to be reminded about…</p>;
      }

      if (context.remindersStatus === "error") {
        return <p>Upcoming reminders could not be refreshed right now.</p>;
      }

      const reminders = (context.upcomingReminders || []).slice(0, 4);

      return reminders.length > 0 ? (
        <ul>
          {reminders.map((reminder, index) => (
            <li key={reminder.id || `${reminder.title}-${index}`}>
              <span className="font-medium">
                {formatReminderDue(reminder.dueAt)}
              </span>
              {reminder.title ? ` — ${reminder.title}` : ""}
            </li>
          ))}
        </ul>
      ) : (
        <p>No upcoming reminders. Ask in chat whenever something should come back at the right time.</p>
      );
    },
  },
  {
    id: "today_brief",
    title: "Today brief",
    icon: CalendarDays,
    modes: CHIEF,
    defaultVisible: true,
    render: (context) => {
      const goals = goalTitles(context.activeGoals);
      const briefingReady = Boolean(context.briefingContent);
      const briefingOpened = Boolean(context.briefingOpenedAt || context.briefingConversationId);

      if (context.status === "loading") {
        return <p>Loading today’s operating context…</p>;
      }
      return briefingReady ? (
        <ul>
          <li>{briefingOpened ? "Briefing thread already opened" : "Briefing ready for review"}</li>
          <li>
            {goals.length} active goal{goals.length === 1 ? "" : "s"} visible
          </li>
          <li>{context.journaledToday ? "Journal signal available" : "No journal signal today"}</li>
        </ul>
      ) : (
        <ul>
          <li>No briefing content yet</li>
          <li>
            {goals.length} active goal{goals.length === 1 ? "" : "s"} visible
          </li>
          <li>Use chat to turn context into priorities</li>
        </ul>
      );
    },
  },
  {
    id: "priority_queue",
    title: "Priority queue",
    icon: CheckCircle2,
    modes: CHIEF,
    defaultVisible: true,
    render: (context) => {
      const goals = goalTitles(context.activeGoals);
      return goals.length > 0 ? (
        <ul>
          {goals.map((goal) => (
            <li key={goal}>{goal}</li>
          ))}
        </ul>
      ) : (
        <p>No active goal is surfaced yet. This section will become your execution queue.</p>
      );
    },
  },
  {
    id: "briefing_topics",
    title: "Briefing topics",
    icon: Newspaper,
    modes: CHIEF,
    defaultVisible: true,
    render: (context) => {
      const briefingSnippet = truncateText(context.briefingContent, 150);
      return briefingSnippet ? (
        <p>{briefingSnippet}</p>
      ) : (
        <p>Economy, banking, AI, tech, market news, or any custom topic you ask the assistant to track.</p>
      );
    },
  },
  {
    id: "risks_blockers",
    title: "Risks & blockers",
    icon: CircleDot,
    modes: CHIEF,
    defaultVisible: true,
    render: (context) => {
      const paused = (context.pausedGoals || []).slice(0, 3);
      if (context.status === "loading") {
        return <p>Scanning for open risks…</p>;
      }
      return paused.length > 0 ? (
        <ul>
          {paused.map((goal, index) => (
            <li key={goal.id || index}>Paused: {goal.title}</li>
          ))}
        </ul>
      ) : (
        <p>No flagged risks right now. Paused goals and stalled follow-ups will surface here when they appear.</p>
      );
    },
  },
];

export function cardsForMode(mode: AssistantMode): WorkspaceCardDefinition[] {
  return WORKSPACE_CARDS.filter((card) => card.modes.includes(mode));
}
