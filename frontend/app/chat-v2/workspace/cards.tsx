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
  MessageCircle,
  Newspaper,
  Target,
  Zap,
  NotebookPen,
  Users,
} from "lucide-react";
import type { ReactNode } from "react";
import type { AssistantMode } from "@/lib/api";
import type { WorkspaceAgendaItem, WorkspaceCardId, WorkspaceContext } from "./types";

export type WorkspaceCardActions = {
  onPrompt?: (prompt: string) => void;
};

export type WorkspaceCardDefinition = {
  id: WorkspaceCardId;
  title: string;
  icon: LucideIcon;
  modes: AssistantMode[];
  defaultVisible: boolean;
  render: (
    context: WorkspaceContext,
    mode: AssistantMode,
    actions?: WorkspaceCardActions,
  ) => ReactNode;
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


type DailyBriefSignal = {
  label: string;
  value: string;
  strong?: boolean;
};

type SuggestedPrompt = {
  label: string;
  intent: string;
  prompt: string;
};

function countLabel(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}

function firstAgendaItem(events: WorkspaceAgendaItem[]): WorkspaceAgendaItem | null {
  const sorted = [...events].sort((a, b) => {
    const left = a.startAt ? new Date(a.startAt).getTime() : Number.MAX_SAFE_INTEGER;
    const right = b.startAt ? new Date(b.startAt).getTime() : Number.MAX_SAFE_INTEGER;
    return left - right;
  });

  return sorted[0] || null;
}

function proactivePanelClass(isChief: boolean): string {
  return [
    "rounded-2xl border p-3",
    isChief
      ? "border-teal-200/15 bg-teal-200/[0.045]"
      : "border-white/70 bg-white/45",
  ].join(" ");
}

function proactiveSignalClass(isChief: boolean, strong = false): string {
  return [
    "rounded-2xl border px-3 py-2",
    isChief
      ? strong
        ? "border-teal-200/20 bg-teal-200/[0.08]"
        : "border-white/10 bg-white/[0.04]"
      : strong
        ? "border-amber-200 bg-amber-50/70"
        : "border-white/70 bg-white/55",
  ].join(" ");
}

function proactiveActionButtonClass(isChief: boolean, primary = false): string {
  return [
    "inline-flex min-h-9 items-center gap-2 rounded-full border px-3 py-2 text-left text-xs font-semibold leading-4 shadow-sm transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
    isChief
      ? primary
        ? "border-teal-200/25 bg-teal-200/[0.11] text-teal-50 hover:bg-teal-200/[0.16]"
        : "border-white/10 bg-white/[0.055] text-slate-300 hover:bg-white/[0.08] hover:text-white"
      : primary
        ? "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100"
        : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
  ].join(" ");
}

function buildDailyBriefSignals(
  context: WorkspaceContext,
  isChief: boolean,
): DailyBriefSignal[] {
  const agenda = context.todayAgenda || [];
  const reminders = context.upcomingReminders || [];
  const goals = context.activeGoals || [];
  const memories = context.recentMemories || [];
  const nextEvent = firstAgendaItem(agenda);
  const nextEventTitle = String(nextEvent?.title || "").trim();

  const signals: DailyBriefSignal[] = [];

  if (agenda.length > 0) {
    signals.push({
      label: isChief ? "Schedule" : "Today",
      value: nextEvent
        ? `${countLabel(agenda.length, "event")} today. Next: ${agendaTimeRange(nextEvent)}${nextEventTitle ? ` — ${nextEventTitle}` : ""}.`
        : `${countLabel(agenda.length, "event")} on today’s calendar.`,
      strong: true,
    });
  } else {
    signals.push({
      label: isChief ? "Schedule" : "Today",
      value: isChief
        ? "No fixed event is surfaced for today. Good window for focused execution."
        : "No fixed event is surfaced for today. There is room to move gently.",
      strong: true,
    });
  }

  if (reminders.length > 0) {
    const firstReminder = reminders[0];
    signals.push({
      label: "Reminders",
      value: `${countLabel(reminders.length, "reminder")} upcoming. Nearest: ${formatReminderDue(firstReminder.dueAt)}${firstReminder.title ? ` — ${firstReminder.title}` : ""}.`,
    });
  } else {
    signals.push({
      label: "Reminders",
      value: "No upcoming reminder is currently surfaced.",
    });
  }

  signals.push({
    label: isChief ? "Execution" : "Goals",
    value:
      goals.length > 0
        ? `${countLabel(goals.length, "active goal")} in view: ${goalTitles(goals).join(", ")}.`
        : isChief
          ? "No active goal is surfaced yet. You can turn today into a short execution queue."
          : "No active goal is surfaced yet. You can still choose one small thing for today.",
  });

  signals.push({
    label: isChief ? "Signals" : "Continuity",
    value: [
      context.journaledToday ? "journal opened today" : "no journal signal today",
      memories.length > 0 ? `${countLabel(memories.length, "recent memory", "recent memories")}` : "no recent memory surfaced",
    ].join(" · "),
  });

  return signals;
}

function buildSuggestedPrompts(
  context: WorkspaceContext,
  mode: AssistantMode,
): SuggestedPrompt[] {
  const isChief = mode === "chief_of_staff";
  const agendaCount = (context.todayAgenda || []).length;
  const reminderCount = (context.upcomingReminders || []).length;
  const goalCount = (context.activeGoals || []).length;
  const peopleCount = (context.people || []).length;

  if (isChief) {
    const prompts: SuggestedPrompt[] = [
      {
        label: "Brief me now",
        intent: "Agenda, risks, and next actions",
        prompt:
          "Aliyya, give me an executive brief for today based on my visible agenda, reminders, goals, and recent context. Structure it into: bottom line, top priorities, risks/blockers, and next actions.",
      },
      {
        label: agendaCount > 0 ? "Prioritize agenda" : "Create focus plan",
        intent: agendaCount > 0 ? `${agendaCount} calendar item${agendaCount === 1 ? "" : "s"}` : "No fixed agenda",
        prompt:
          agendaCount > 0
            ? "Aliyya, prioritize my agenda today. Separate items into decision, follow-up, deep work, and low-priority. Then give me the recommended order."
            : "Aliyya, help me create a focused execution plan for today with 3 priorities, estimated time blocks, and one thing to avoid.",
      },
      {
        label: reminderCount > 0 ? "Review reminders" : "Set execution rhythm",
        intent: reminderCount > 0 ? `${reminderCount} reminder${reminderCount === 1 ? "" : "s"}` : "No reminders",
        prompt:
          reminderCount > 0
            ? "Aliyya, review my upcoming reminders and turn them into a practical action list with urgency and owner/next step."
            : "Aliyya, suggest a practical check-in rhythm for today so I do not lose track of important follow-ups.",
      },
    ];

    return prompts;
  }

  const prompts: SuggestedPrompt[] = [
    {
      label: "Gentle check-in",
      intent: context.journaledToday ? "Continue today’s reflection" : "Start softly",
      prompt:
        "Aliyya, help me do a gentle check-in for today. Ask me a few light questions, then help me choose one small next step.",
    },
    {
      label: goalCount > 0 ? "Choose one step" : "Make today lighter",
      intent: goalCount > 0 ? `${goalCount} active goal${goalCount === 1 ? "" : "s"}` : "No active goal",
      prompt:
        goalCount > 0
          ? "Aliyya, look at my active goals and help me choose one realistic step for today without making it feel heavy."
          : "Aliyya, help me make today feel lighter. Suggest one simple plan based on what you know about me.",
    },
    {
      label: peopleCount > 0 ? "Personal follow-up" : "Reflect and reset",
      intent: peopleCount > 0 ? `${peopleCount} people in context` : "Quiet continuity",
      prompt:
        peopleCount > 0
          ? "Aliyya, based on the people who matter in my context, is there anyone I should gently follow up with today?"
          : "Aliyya, help me reflect and reset. Keep it warm, short, and practical.",
    },
  ];

  return prompts;
}

function ProactiveDailyBriefCard({
  context,
  mode,
  actions,
}: {
  context: WorkspaceContext;
  mode: AssistantMode;
  actions?: WorkspaceCardActions;
}) {
  const isChief = mode === "chief_of_staff";
  const assistantName = String(context.assistantName || "").trim() || "Aliyya";
  const isLoading =
    context.status === "loading" ||
    context.agendaStatus === "loading" ||
    context.remindersStatus === "loading";

  if (isLoading) {
    return <p>{assistantName} is assembling today’s signals…</p>;
  }

  if (context.status === "error") {
    return <p>{assistantName} could not load the full context yet, but the chat is still ready.</p>;
  }

  const signals = buildDailyBriefSignals(context, isChief);
  const primaryPrompt = isChief
    ? "Aliyya, give me an executive brief for today based on my visible agenda, reminders, goals, and recent context. Structure it into: bottom line, top priorities, risks/blockers, and next actions."
    : "Aliyya, give me a gentle daily brief for today based on my visible agenda, reminders, goals, and recent context. Keep it warm, practical, and light.";

  return (
    <div className="space-y-3">
      <div className={proactivePanelClass(isChief)}>
        <p className={isChief ? "text-sm leading-6 text-slate-300" : "text-sm leading-6 text-stone-600"}>
          {isChief
            ? `${assistantName} has a quick operating picture ready from today’s visible context.`
            : `${assistantName} has a soft daily picture ready from today’s visible context.`}
        </p>
      </div>

      <div className="grid gap-2">
        {signals.map((signal) => (
          <div key={signal.label} className={proactiveSignalClass(isChief, signal.strong)}>
            <p className={isChief ? "text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500" : "text-[10px] font-bold uppercase tracking-[0.18em] text-stone-400"}>
              {signal.label}
            </p>
            <p className={isChief ? "mt-1 text-sm leading-5 text-slate-200" : "mt-1 text-sm leading-5 text-stone-700"}>
              {signal.value}
            </p>
          </div>
        ))}
      </div>

      <button
        type="button"
        disabled={!actions?.onPrompt}
        onClick={() => actions?.onPrompt?.(primaryPrompt)}
        className={proactiveActionButtonClass(isChief, true)}
      >
        <MessageCircle className="h-3.5 w-3.5 shrink-0" />
        {isChief ? "Ask for executive brief" : "Ask for gentle brief"}
      </button>
    </div>
  );
}

function ProactiveNextActionsCard({
  context,
  mode,
  actions,
}: {
  context: WorkspaceContext;
  mode: AssistantMode;
  actions?: WorkspaceCardActions;
}) {
  const isChief = mode === "chief_of_staff";
  const prompts = buildSuggestedPrompts(context, mode);

  if (context.status === "loading") {
    return <p>Preparing proactive suggestions…</p>;
  }

  return (
    <div className="space-y-2">
      {prompts.map((item, index) => (
        <button
          key={item.label}
          type="button"
          disabled={!actions?.onPrompt}
          onClick={() => actions?.onPrompt?.(item.prompt)}
          className={proactiveActionButtonClass(isChief, index === 0)}
        >
          <Target className="h-3.5 w-3.5 shrink-0" />
          <span className="min-w-0">
            <span className="block">{item.label}</span>
            <span className={isChief ? "block text-[11px] font-normal text-slate-500" : "block text-[11px] font-normal text-stone-500"}>
              {item.intent}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}



type MemoryInsightRow = {
  label: string;
  value: string;
  detail?: string;
  strong?: boolean;
};

function formatRelativeMemoryDate(value: string | null | undefined): string | null {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.max(0, Math.floor(diffMs / 86_400_000));

  if (diffDays === 0) return "today";
  if (diffDays === 1) return "yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 31) return `${Math.floor(diffDays / 7)} week${Math.floor(diffDays / 7) === 1 ? "" : "s"} ago`;
  if (diffDays < 365) return `${Math.floor(diffDays / 30)} month${Math.floor(diffDays / 30) === 1 ? "" : "s"} ago`;
  return `${Math.floor(diffDays / 365)} year${Math.floor(diffDays / 365) === 1 ? "" : "s"} ago`;
}

function memoryIntelligencePanelClass(isChief: boolean, strong = false): string {
  return [
    "rounded-2xl border px-3 py-2.5",
    isChief
      ? strong
        ? "border-teal-200/20 bg-teal-200/[0.08]"
        : "border-white/10 bg-white/[0.04]"
      : strong
        ? "border-amber-200 bg-amber-50/70"
        : "border-white/70 bg-white/55",
  ].join(" ");
}

function memoryIntelligenceLabelClass(isChief: boolean): string {
  return [
    "text-[10px] font-bold uppercase tracking-[0.18em]",
    isChief ? "text-slate-500" : "text-stone-400",
  ].join(" ");
}

function memoryIntelligenceTextClass(isChief: boolean): string {
  return [
    "mt-1 text-sm leading-5",
    isChief ? "text-slate-200" : "text-stone-700",
  ].join(" ");
}

function memoryIntelligenceMetaClass(isChief: boolean): string {
  return [
    "mt-1 text-xs leading-5",
    isChief ? "text-slate-500" : "text-stone-500",
  ].join(" ");
}

function memoryActionButtonClass(isChief: boolean, primary = false): string {
  return [
    "inline-flex min-h-9 items-center gap-2 rounded-full border px-3 py-2 text-left text-xs font-semibold leading-4 shadow-sm transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50",
    isChief
      ? primary
        ? "border-teal-200/25 bg-teal-200/[0.11] text-teal-50 hover:bg-teal-200/[0.16]"
        : "border-white/10 bg-white/[0.055] text-slate-300 hover:bg-white/[0.08] hover:text-white"
      : primary
        ? "border-amber-200 bg-amber-50 text-amber-800 hover:bg-amber-100"
        : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
  ].join(" ");
}

function buildMemoryInsightRows(
  context: WorkspaceContext,
  isChief: boolean,
): MemoryInsightRow[] {
  const memories = context.recentMemories || [];
  const people = context.people || [];
  const activeGoals = context.activeGoals || [];
  const pausedGoals = context.pausedGoals || [];
  const newestMemory = memories[0];
  const newestMemoryAge = formatRelativeMemoryDate(newestMemory?.createdAt);

  const rows: MemoryInsightRow[] = [
    {
      label: isChief ? "Memory freshness" : "Recent memory",
      value:
        newestMemory && newestMemory.content
          ? truncateText(newestMemory.content, 120) || "Recent memory is available."
          : "No recent memory is surfaced yet.",
      detail: newestMemoryAge ? `Last surfaced: ${newestMemoryAge}` : "Freshness depends on saved memory timestamps.",
      strong: Boolean(newestMemory),
    },
    {
      label: isChief ? "Relationship context" : "People in reach",
      value:
        people.length > 0
          ? `${countLabel(people.length, "person", "people")} in context: ${people
              .map((person) => person.name)
              .filter(Boolean)
              .slice(0, 3)
              .join(", ")}.`
          : "No relationship context is surfaced yet.",
      detail:
        people.length > 0
          ? "Useful for follow-ups, tone, and continuity."
          : "People added later will become relationship signals.",
    },
    {
      label: isChief ? "Project signal" : "Life thread",
      value:
        activeGoals.length > 0
          ? `${countLabel(activeGoals.length, "active goal")} visible: ${goalTitles(activeGoals).join(", ")}.`
          : "No active goal is surfaced yet.",
      detail:
        pausedGoals.length > 0
          ? `${countLabel(pausedGoals.length, "paused goal")} may need review.`
          : isChief
            ? "No paused goal is currently flagged."
            : "No stuck thread is currently flagged.",
    },
    {
      label: isChief ? "Daily continuity" : "Today’s signal",
      value: context.journaledToday
        ? "Journal signal exists for today."
        : "No journal signal is available today.",
      detail: context.briefingContent
        ? "Briefing content is also available."
        : "Briefing content is not available yet.",
    },
  ];

  return rows;
}

function MemoryIntelligenceCard({
  context,
  mode,
  actions,
}: {
  context: WorkspaceContext;
  mode: AssistantMode;
  actions?: WorkspaceCardActions;
}) {
  const isChief = mode === "chief_of_staff";
  const assistantName = String(context.assistantName || "").trim() || "Aliyya";

  if (context.status === "loading") {
    return <p>{assistantName} is checking memory freshness and continuity signals…</p>;
  }

  if (context.status === "error") {
    return <p>Memory signals could not be loaded yet. The chat remains available.</p>;
  }

  const rows = buildMemoryInsightRows(context, isChief);
  const prompt = isChief
    ? "Aliyya, review my current memory intelligence signals. Identify what is fresh, what may be stale, what relationship context matters, and what project/thread should be prioritized next."
    : "Aliyya, review my current memory and continuity signals gently. Help me notice what feels important, what may be outdated, and one small thing to follow up on.";

  return (
    <div className="space-y-3">
      <div className="grid gap-2">
        {rows.map((row) => (
          <div key={row.label} className={memoryIntelligencePanelClass(isChief, row.strong)}>
            <p className={memoryIntelligenceLabelClass(isChief)}>{row.label}</p>
            <p className={memoryIntelligenceTextClass(isChief)}>{row.value}</p>
            {row.detail ? <p className={memoryIntelligenceMetaClass(isChief)}>{row.detail}</p> : null}
          </div>
        ))}
      </div>

      <button
        type="button"
        disabled={!actions?.onPrompt}
        onClick={() => actions?.onPrompt?.(prompt)}
        className={memoryActionButtonClass(isChief, true)}
      >
        <Brain className="h-3.5 w-3.5 shrink-0" />
        {isChief ? "Analyze memory signals" : "Review gently with Aliyya"}
      </button>
    </div>
  );
}

function RelationshipRadarCard({
  context,
  mode,
  actions,
}: {
  context: WorkspaceContext;
  mode: AssistantMode;
  actions?: WorkspaceCardActions;
}) {
  const isChief = mode === "chief_of_staff";
  const people = (context.people || []).slice(0, 4);

  if (context.status === "loading") {
    return <p>Scanning relationship context…</p>;
  }

  const prompt = isChief
    ? "Aliyya, review the people currently in my context. Suggest who may need a follow-up, what the likely purpose is, and how to keep it concise and professional."
    : "Aliyya, look at the people currently in my context. Is there anyone I should gently check in with today? Keep it warm and low-pressure.";

  return (
    <div className="space-y-3">
      {people.length > 0 ? (
        <div className="grid gap-2">
          {people.map((person, index) => (
            <div
              key={person.id || person.name || index}
              className={memoryIntelligencePanelClass(isChief, index === 0)}
            >
              <p className={memoryIntelligenceLabelClass(isChief)}>
                {person.relationship || "Relationship"}
              </p>
              <p className={memoryIntelligenceTextClass(isChief)}>
                {person.name || "Unnamed person"}
              </p>
              <p className={memoryIntelligenceMetaClass(isChief)}>
                {isChief
                  ? "Available for follow-up planning and stakeholder context."
                  : "Available for gentle continuity and personal check-ins."}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <div className={memoryIntelligencePanelClass(isChief, true)}>
          <p className={memoryIntelligenceTextClass(isChief)}>
            No people are surfaced yet. People you add later can become follow-up and relationship signals.
          </p>
        </div>
      )}

      <button
        type="button"
        disabled={!actions?.onPrompt}
        onClick={() => actions?.onPrompt?.(prompt)}
        className={memoryActionButtonClass(isChief, true)}
      >
        <Users className="h-3.5 w-3.5 shrink-0" />
        {isChief ? "Plan stakeholder follow-up" : "Suggest a gentle check-in"}
      </button>
    </div>
  );
}

function ProjectTrackerCard({
  context,
  mode,
  actions,
}: {
  context: WorkspaceContext;
  mode: AssistantMode;
  actions?: WorkspaceCardActions;
}) {
  const isChief = mode === "chief_of_staff";
  const activeGoals = (context.activeGoals || []).slice(0, 4);
  const pausedGoals = (context.pausedGoals || []).slice(0, 3);

  if (context.status === "loading") {
    return <p>Checking active threads and paused goals…</p>;
  }

  const prompt = isChief
    ? "Aliyya, turn my visible goals and paused threads into a project tracker. Give me status, risk, next action, and what should be ignored for now."
    : "Aliyya, help me review my visible goals gently. Pick one realistic next step and tell me what I can leave for later.";

  return (
    <div className="space-y-3">
      {activeGoals.length > 0 ? (
        <div className="grid gap-2">
          {activeGoals.map((goal, index) => (
            <div
              key={goal.id || goal.title || index}
              className={memoryIntelligencePanelClass(isChief, index === 0)}
            >
              <p className={memoryIntelligenceLabelClass(isChief)}>
                {isChief ? "Active thread" : "Active goal"}
              </p>
              <p className={memoryIntelligenceTextClass(isChief)}>
                {goal.title || "Untitled goal"}
              </p>
              <p className={memoryIntelligenceMetaClass(isChief)}>
                {isChief ? "Ready for next-action sizing." : "Available as one possible focus."}
              </p>
            </div>
          ))}
        </div>
      ) : (
        <div className={memoryIntelligencePanelClass(isChief, true)}>
          <p className={memoryIntelligenceTextClass(isChief)}>
            No active goal is surfaced yet. This can still become a lightweight project tracker once goals are added.
          </p>
        </div>
      )}

      {pausedGoals.length > 0 ? (
        <div className={memoryIntelligencePanelClass(isChief)}>
          <p className={memoryIntelligenceLabelClass(isChief)}>
            {isChief ? "Potential blockers" : "Paused threads"}
          </p>
          <p className={memoryIntelligenceTextClass(isChief)}>
            {pausedGoals.map((goal) => goal.title).filter(Boolean).join(", ")}
          </p>
        </div>
      ) : null}

      <button
        type="button"
        disabled={!actions?.onPrompt}
        onClick={() => actions?.onPrompt?.(prompt)}
        className={memoryActionButtonClass(isChief, true)}
      >
        <CheckCircle2 className="h-3.5 w-3.5 shrink-0" />
        {isChief ? "Build project tracker" : "Choose one next step"}
      </button>
    </div>
  );
}


export const WORKSPACE_CARDS: WorkspaceCardDefinition[] = [
  {
    id: "proactive_daily_brief",
    title: "Aliyya Daily Brief",
    icon: Zap,
    modes: BOTH,
    defaultVisible: true,
    render: (context, mode, actions) => (
      <ProactiveDailyBriefCard context={context} mode={mode} actions={actions} />
    ),
  },
  {
    id: "proactive_next_actions",
    title: "Proactive next moves",
    icon: MessageCircle,
    modes: BOTH,
    defaultVisible: true,
    render: (context, mode, actions) => (
      <ProactiveNextActionsCard context={context} mode={mode} actions={actions} />
    ),
  },
  {
    id: "memory_intelligence",
    title: "Memory Intelligence",
    icon: Brain,
    modes: BOTH,
    defaultVisible: true,
    render: (context, mode, actions) => (
      <MemoryIntelligenceCard context={context} mode={mode} actions={actions} />
    ),
  },
  {
    id: "relationship_radar",
    title: "Relationship Radar",
    icon: Users,
    modes: BOTH,
    defaultVisible: true,
    render: (context, mode, actions) => (
      <RelationshipRadarCard context={context} mode={mode} actions={actions} />
    ),
  },
  {
    id: "project_tracker",
    title: "Project Tracker",
    icon: CheckCircle2,
    modes: BOTH,
    defaultVisible: true,
    render: (context, mode, actions) => (
      <ProjectTrackerCard context={context} mode={mode} actions={actions} />
    ),
  },
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
                    href={`/calendar?event=${encodeURIComponent(String(event.id || ""))}`}
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
