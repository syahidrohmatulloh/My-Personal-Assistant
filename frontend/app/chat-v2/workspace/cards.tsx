import type { LucideIcon } from "lucide-react";
import {
  AlarmClock,
  Brain,
  ArrowUpRight,
  CalendarDays,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
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
import type { WorkspaceAgendaItem, WorkspaceCardId, WorkspaceContext } from "./types";

export type WorkspaceCardDefinition = {
  id: WorkspaceCardId;
  title: string;
  icon: LucideIcon;
  modes: AssistantMode[];
  defaultVisible: boolean;
  render: (context: WorkspaceContext, mode: AssistantMode) => ReactNode;
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

const GOOGLE_CALENDAR_URL = "https://calendar.google.com/calendar/u/0/r";

function agendaTimeRange(event: WorkspaceAgendaItem): string {
  if (event.allDay) return "All day";

  const start = formatClock(event.startAt);
  const end = formatClock(event.endAt);

  if (start && end) return `${start}–${end}`;
  return start || end || "Time pending";
}

function agendaSourceLabel(source: WorkspaceAgendaItem["source"]): string {
  if (source === "google") return "Google";
  if (source === "synced") return "Synced";
  return "Local";
}

function agendaToolbarButtonClass(isChief: boolean): string {
  return [
    "inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[11px] font-semibold shadow-sm transition active:scale-[0.98]",
    isChief
      ? "border-white/10 bg-white/[0.06] text-slate-300 hover:border-teal-200/25 hover:bg-teal-200/[0.09] hover:text-teal-100"
      : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
  ].join(" ");
}

function agendaPanelClass(isChief: boolean): string {
  return [
    "overflow-hidden rounded-2xl border backdrop-blur",
    isChief
      ? "border-white/10 bg-white/[0.045] shadow-[inset_0_1px_0_rgba(255,255,255,0.05)]"
      : "border-white/70 bg-white/45",
  ].join(" ");
}

function agendaRowBaseClass(isChief: boolean): string {
  return [
    "group grid grid-cols-[4.35rem_1fr_auto] items-center gap-3 px-3 py-3 text-left no-underline transition",
    isChief
      ? "hover:bg-teal-200/[0.07]"
      : "hover:bg-white/65",
  ].join(" ");
}

function agendaRowDividerClass(isChief: boolean): string {
  return isChief ? "border-t border-white/10" : "border-t border-white/70";
}

function agendaTimeClass(isChief: boolean): string {
  return [
    "font-mono text-[11px] font-semibold leading-4 tabular-nums",
    isChief ? "text-slate-400" : "text-stone-500",
  ].join(" ");
}

function agendaTitleClass(isChief: boolean): string {
  return [
    "block truncate text-sm font-semibold leading-5",
    isChief ? "text-slate-100" : "text-stone-950",
  ].join(" ");
}

function agendaMetaClass(isChief: boolean): string {
  return [
    "block truncate text-xs leading-5",
    isChief ? "text-slate-400" : "text-stone-500",
  ].join(" ");
}

function agendaSourceBadgeClass(
  source: WorkspaceAgendaItem["source"],
  isChief = false,
): string {
  if (source === "google") {
    return isChief
      ? "border-teal-300/25 bg-teal-300/[0.12] text-teal-100"
      : "border-emerald-200 bg-emerald-50 text-emerald-700";
  }

  if (source === "synced") {
    return isChief
      ? "border-lime-300/25 bg-lime-300/[0.12] text-lime-100"
      : "border-lime-200 bg-lime-50 text-lime-700";
  }

  return isChief
    ? "border-violet-300/25 bg-violet-300/[0.12] text-violet-100"
    : "border-indigo-200 bg-indigo-50 text-indigo-700";
}

function agendaChevronClass(isChief: boolean): string {
  return [
    "h-3.5 w-3.5 transition group-hover:translate-x-0.5",
    isChief ? "text-slate-500 group-hover:text-teal-200" : "text-stone-300 group-hover:text-stone-500",
  ].join(" ");
}

function agendaEmptyClass(isChief: boolean): string {
  return [
    "rounded-2xl border border-dashed px-4 py-5",
    isChief ? "border-white/10 bg-white/[0.035] text-slate-400" : "border-stone-200 bg-white/35",
  ].join(" ");
}

function agendaFootnoteClass(isChief: boolean): string {
  return [
    "text-xs leading-5",
    isChief ? "text-slate-500" : "text-stone-500",
  ].join(" ");
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
    render: (context, mode) => {
      const isChief = mode === "chief_of_staff";

      if (context.status === "loading" || context.agendaStatus === "loading") {
        return <p>Bringing today’s schedule into focus…</p>;
      }

      if (context.agendaStatus === "error") {
        return <p>Today’s agenda could not be refreshed. The rest of your workspace is still available.</p>;
      }

      const agenda = (context.todayAgenda || []).slice(0, 4);

      return (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <a href="/calendar" className={agendaToolbarButtonClass(isChief)}>
              <CalendarDays className="h-3.5 w-3.5" />
              Calendar page
            </a>
            <a
              href={GOOGLE_CALENDAR_URL}
              target="_blank"
              rel="noreferrer"
              className={agendaToolbarButtonClass(isChief)}
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Google Calendar
            </a>
          </div>

          {agenda.length > 0 ? (
            <div className={agendaPanelClass(isChief)}>
              {agenda.map((event, index) => {
                const time = agendaTimeRange(event);
                const title = String(event.title || "Calendar event").trim();
                const source = event.source || "local";
                const [startTime, endTime] = time.split("–");

                return (
                  <a
                    key={event.id || `${event.title}-${index}`}
                    href="/calendar"
                    className={[
                      agendaRowBaseClass(isChief),
                      index > 0 ? agendaRowDividerClass(isChief) : "",
                    ].join(" ")}
                  >
                    <span className={agendaTimeClass(isChief)}>
                      <span className="block">{startTime}</span>
                      {endTime ? <span className="block opacity-70">{endTime}</span> : null}
                    </span>

                    <span className="min-w-0">
                      <span className={agendaTitleClass(isChief)}>{title}</span>
                      {event.location ? (
                        <span className={agendaMetaClass(isChief)}>{event.location}</span>
                      ) : (
                        <span className={agendaMetaClass(isChief)}>{agendaSourceLabel(source)}</span>
                      )}
                    </span>

                    <span className="flex items-center gap-2">
                      <span
                        className={[
                          "rounded-full border px-2 py-0.5 text-[9px] font-bold uppercase tracking-[0.14em]",
                          agendaSourceBadgeClass(source, isChief),
                        ].join(" ")}
                      >
                        {agendaSourceLabel(source)}
                      </span>
                      <ChevronRight className={agendaChevronClass(isChief)} />
                    </span>
                  </a>
                );
              })}
            </div>
          ) : (
            <div className={agendaEmptyClass(isChief)}>
              <p>No confirmed events are scheduled here for today. You can ask the assistant to add or organize one.</p>
            </div>
          )}

          {agenda.some((event) => event.source === "local") ? (
            <p className={agendaFootnoteClass(isChief)}>
              Local-only items can be synced from the Calendar page or by asking Aliyya in chat.
            </p>
          ) : null}
        </div>
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
