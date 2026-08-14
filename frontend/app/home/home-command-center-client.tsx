"use client";

import Link from "next/link";
import {
  ArrowRight,
  Bell,
  Brain,
  BriefcaseBusiness,
  CalendarDays,
  CircleDot,
  Heart,
  MessageCircle,
  Mic,
  Sparkles,
  Target,
  Users,
} from "lucide-react";
import { type ReactNode, useEffect, useMemo, useState } from "react";
import { getCompanionSettings, patchCompanionSettings } from "@/lib/api";
import { loadAssistantWorkspaceContext } from "@/lib/assistant-context/load-workspace-context";
import { saveChatV2Handoff } from "@/lib/chat-handoff";
import type {
  WorkspaceAgendaItem,
  WorkspaceContext,
  WorkspaceGoal,
  WorkspaceMemory,
  WorkspacePerson,
  WorkspaceReminder,
} from "@/lib/assistant-context/types";
import {
  ASSISTANT_MODE_EVENT,
  changeAssistantMode,
  extractAssistantMode,
} from "../chat-v2/mode-events";

type AssistantMode = "life_companion" | "chief_of_staff";

const ASSISTANT_NAME_CACHE_KEY = "app:assistant-name";

function cleanAssistantName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value
    .trim()
    .replace(/^(sekarang|jadi|menjadi|adalah|namanya|itu)\s+/i, "")
    .trim();

  return cleaned.length > 0 ? cleaned : null;
}

function readCachedAssistantName(): string | null {
  if (typeof window === "undefined") return null;

  try {
    return cleanAssistantName(window.localStorage.getItem(ASSISTANT_NAME_CACHE_KEY));
  } catch {
    return null;
  }
}

function readCachedMode(): AssistantMode {
  if (typeof window === "undefined") return "life_companion";

  try {
    const saved = window.localStorage.getItem("aliyya.chatV2.mode");
    return saved === "chief_of_staff" ? "chief_of_staff" : "life_companion";
  } catch {
    return "life_companion";
  }
}

function emptyWorkspaceContext(assistantName?: string | null): WorkspaceContext {
  return {
    status: "loading",
    briefingContent: null,
    briefingOpenedAt: null,
    briefingConversationId: null,
    journaledToday: false,
    activeGoals: [],
    pausedGoals: [],
    people: [],
    recentMemories: [],
    todayAgenda: [],
    upcomingReminders: [],
    agendaStatus: "loading",
    remindersStatus: "loading",
    sourceHealth: [
      { id: "agenda", label: "Calendar", status: "loading", detail: "Loading calendar" },
      { id: "reminders", label: "Reminders", status: "loading", detail: "Loading reminders" },
      { id: "brief", label: "Brief", status: "loading", detail: "Loading brief" },
      { id: "journal", label: "Journal", status: "loading", detail: "Loading journal" },
      { id: "goals", label: "Goals", status: "loading", detail: "Loading goals" },
      { id: "memories", label: "Memory", status: "loading", detail: "Loading memory" },
      { id: "people", label: "People", status: "loading", detail: "Loading people" },
    ],
    assistantName: assistantName ?? null,
  };
}

function getGreeting(now = new Date()): string {
  const hour = now.getHours();

  if (hour < 11) return "Selamat pagi";
  if (hour < 15) return "Selamat siang";
  if (hour < 18) return "Selamat sore";
  return "Selamat malam";
}

function formatDayTime(now = new Date()): string {
  return new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    hour: "2-digit",
    minute: "2-digit",
  })
    .format(now)
    .replace(".", ":")
    .toUpperCase();
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

function formatDateTime(value: string | null | undefined): string | null {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  const today = new Date();
  const sameDay =
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate();

  if (sameDay) {
    return `Hari ini ${formatClock(value) || ""}`.trim();
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

function truncateText(value: string | null | undefined, maxLength = 110): string {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength - 1).trim()}…`;
}

function getModeCopy(mode: AssistantMode, assistantName: string) {
  if (mode === "chief_of_staff") {
    return {
      eyebrow: "Chief of Staff command center",
      title: "Your day, structured before the first message.",
      summary:
        "Agenda, goals, reminders, and unresolved threads stay visible here. Continue into chat when you need execution.",
      prompt: `Ask ${assistantName} to brief, prioritize, or turn this into action...`,
      primary: "Open execution chat",
      secondary: "Review priorities",
    };
  }

  return {
    eyebrow: "Life Companion command center",
    title: "Calm overview before you start talking.",
    summary:
      "A calm entry point for what matters now.",
    prompt: `Cerita apa pun ke ${assistantName}...`,
    primary: "Start chat",
    secondary: "Start reflection",
  };
}

function buildLiveSummary(context: WorkspaceContext, assistantName: string, isChief: boolean): string {
  const agendaCount = context.todayAgenda?.length ?? 0;
  const reminderCount = context.upcomingReminders?.length ?? 0;
  const goalCount = context.activeGoals?.length ?? 0;

  if (context.status === "loading") return "Loading your live context…";

  if (isChief) {
    if (agendaCount || reminderCount || goalCount) {
      return `${agendaCount} agenda, ${reminderCount} reminders, ${goalCount} active goals are surfaced for execution.`;
    }

    return "No heavy operating signal is surfaced yet. Clean window for focused execution.";
  }

  if (agendaCount || reminderCount) {
    return `${assistantName} sees ${agendaCount} agenda item${agendaCount === 1 ? "" : "s"} and ${reminderCount} reminder${reminderCount === 1 ? "" : "s"} waiting gently.`;
  }

  if (context.journaledToday) {
    return `${assistantName} can continue from your journal signal today.`;
  }

  return "Tidak ada yang terlalu mendesak dari sinyal yang terlihat sekarang.";
}

function buildHomeOffers(context: WorkspaceContext, mode: AssistantMode, assistantName: string) {
  const agendaCount = context.todayAgenda?.length ?? 0;
  const reminderCount = context.upcomingReminders?.length ?? 0;
  const goalCount = context.activeGoals?.length ?? 0;

  if (mode === "chief_of_staff") {
    return [
      agendaCount > 0 ? "Brief me for today’s agenda" : "Create a focus plan",
      goalCount > 0 ? "Prioritize active goals" : "Set execution priorities",
      reminderCount > 0 ? "Review reminders and blockers" : "Find hidden blockers",
    ];
  }

  return [
    context.journaledToday ? "Lanjutkan refleksi hari ini" : "Tulis refleksi singkat",
    agendaCount > 0 ? "Bantu jalani agenda hari ini" : "Apa yang perlu ditengok?",
    reminderCount > 0 ? `Ubah reminder jadi langkah kecil` : `Cerita pelan-pelan ke ${assistantName}`,
  ];
}

function statusLabel(status: WorkspaceContext["agendaStatus"] | WorkspaceContext["remindersStatus"]): string {
  if (status === "loading") return "Loading";
  if (status === "error") return "Stale";
  return "Live";
}

function healthStatusClass(status: string, isChief: boolean): string {
  if (status === "failed") {
    return isChief
      ? "border-rose-300/20 bg-rose-300/[0.08] text-rose-100"
      : "border-rose-200 bg-rose-50 text-rose-700";
  }

  if (status === "loading" || status === "stale") {
    return isChief
      ? "border-amber-300/20 bg-amber-300/[0.08] text-amber-100"
      : "border-amber-200 bg-amber-50 text-amber-700";
  }

  if (status === "empty") {
    return isChief
      ? "border-slate-300/15 bg-white/[0.045] text-slate-300"
      : "border-stone-200 bg-white/60 text-stone-600";
  }

  return isChief
    ? "border-teal-300/20 bg-teal-300/[0.08] text-teal-100"
    : "border-emerald-200 bg-emerald-50 text-emerald-700";
}

function healthStatusDotClass(status: string, isChief: boolean): string {
  if (status === "failed") return isChief ? "bg-rose-200" : "bg-rose-500";
  if (status === "loading" || status === "stale") return isChief ? "bg-amber-200" : "bg-amber-500";
  if (status === "empty") return isChief ? "bg-slate-400" : "bg-stone-400";
  return isChief ? "bg-teal-200" : "bg-emerald-500";
}

function healthStatusLabel(status: string): string {
  if (status === "failed") return "Failed";
  if (status === "loading") return "Loading";
  if (status === "stale") return "Stale";
  if (status === "empty") return "Empty";
  return "Live";
}

function agendaTitle(item: WorkspaceAgendaItem): string {
  return truncateText(item.title || "Untitled event", 80);
}

function agendaDetail(item: WorkspaceAgendaItem): string {
  const time =
    item.allDay
      ? "All day"
      : [formatClock(item.startAt), formatClock(item.endAt)].filter(Boolean).join("–") ||
        "Time pending";
  const meta = [time, item.location, item.source === "google" ? "Google" : item.source]
    .filter(Boolean)
    .join(" · ");

  return meta || "Calendar item";
}

function reminderTitle(item: WorkspaceReminder): string {
  return truncateText(item.title || item.message || "Reminder", 80);
}

function reminderDetail(item: WorkspaceReminder): string {
  return [formatDateTime(item.dueAt), truncateText(item.message, 70)]
    .filter(Boolean)
    .join(" · ") || "Reminder";
}

function memoryTitle(item: WorkspaceMemory): string {
  return truncateText(item.content || "Memory", 88);
}

function memoryDetail(item: WorkspaceMemory): string {
  return item.kind ? item.kind[0].toUpperCase() + item.kind.slice(1) : "Memory";
}

function personTitle(item: WorkspacePerson): string {
  return truncateText(item.name || "Person", 80);
}

function personDetail(item: WorkspacePerson): string {
  return item.relationship ? truncateText(item.relationship, 80) : "Relationship context";
}

function goalTitle(item: WorkspaceGoal): string {
  return truncateText(item.title || "Goal", 82);
}

function goalDetail(item: WorkspaceGoal): string {
  return item.status ? item.status[0].toUpperCase() + item.status.slice(1) : "Active";
}

export function HomeCommandCenterClient() {
  const [mode, setModeState] = useState<AssistantMode>("life_companion");
  const [assistantName, setAssistantName] = useState<string>(() => readCachedAssistantName() ?? "Hana");
  const [now, setNow] = useState<Date | null>(null);
  const [handoffInput, setHandoffInput] = useState("");
  const [workspaceContext, setWorkspaceContext] = useState<WorkspaceContext>(() =>
    emptyWorkspaceContext(readCachedAssistantName() ?? "Hana"),
  );

  useEffect(() => {
    setModeState(readCachedMode());

    let cancelled = false;

    getCompanionSettings()
      .then((settings) => {
        if (cancelled) return;

        const nextMode = extractAssistantMode(settings);
        if (nextMode) setModeState(nextMode);

        const nextName = cleanAssistantName(settings.assistant_name);
        if (nextName) {
          setAssistantName(nextName);
          setWorkspaceContext((current) => ({ ...current, assistantName: nextName }));
        }
      })
      .catch(() => {
        // Home shell stays available even if companion settings are temporarily unavailable.
      });

    function onModeEvent(event: Event) {
      const detail = (event as CustomEvent).detail;
      const nextMode = extractAssistantMode(detail);
      if (nextMode) setModeState(nextMode);
    }

    window.addEventListener(ASSISTANT_MODE_EVENT, onModeEvent);

    const timer = window.setInterval(() => setNow(new Date()), 30_000);

    return () => {
      cancelled = true;
      window.removeEventListener(ASSISTANT_MODE_EVENT, onModeEvent);
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function refreshWorkspace(showLoading = false) {
      if (showLoading) {
        setWorkspaceContext((current) => ({
          ...current,
          status: "loading",
          agendaStatus: "loading",
          remindersStatus: "loading",
        }));
      }

      try {
        const next = await loadAssistantWorkspaceContext({
          assistantName: readCachedAssistantName() ?? assistantName,
        });

        if (cancelled) return;

        setWorkspaceContext(next);
      } catch {
        if (cancelled) return;

        setWorkspaceContext((current) => ({
          ...current,
          status: "error",
          agendaStatus: "error",
          remindersStatus: "error",
        }));
      }
    }

    void refreshWorkspace(true);
    const timer = window.setInterval(() => void refreshWorkspace(false), 60_000);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  const contextWithName = useMemo<WorkspaceContext>(
    () => ({
      ...workspaceContext,
      assistantName,
    }),
    [assistantName, workspaceContext],
  );
  const copy = useMemo(() => getModeCopy(mode, assistantName), [assistantName, mode]);
  const isChief = mode === "chief_of_staff";
  const greeting = now ? getGreeting(now) : "";
  const dayTime = now ? formatDayTime(now) : "";
  const liveSummary = buildLiveSummary(contextWithName, assistantName, isChief);
  const offers = buildHomeOffers(contextWithName, mode, assistantName);

  function openChatWithHandoff(text: string, label = "home") {
    const cleaned = text.replace(/\s+/g, " ").trim();

    if (cleaned) {
      saveChatV2Handoff({
        source: "home",
        text: cleaned,
        mode,
        label,
      });
    }

    window.location.assign("/chat-v2");
  }

  function submitHandoff(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    openChatWithHandoff(handoffInput, "home-composer");
  }

  function offerPrompt(label: string): string {
    if (mode === "chief_of_staff") {
      return `${assistantName}, ${label}. Use my visible Home context — agenda, reminders, goals, memory, people, and daily brief — and turn it into a concise execution plan.`;
    }

    return `${assistantName}, ${label}. Use my visible Home context gently and help me continue from there.`;
  }

  function applyModeLocally(nextMode: AssistantMode) {
    setModeState(nextMode);

    try {
      window.localStorage.setItem("aliyya.chatV2.mode", nextMode);
    } catch {}
  }

  function setMode(nextMode: AssistantMode) {
    void changeAssistantMode(nextMode, {
      applyLocally: applyModeLocally,
      persist: (mode) => patchCompanionSettings({ assistant_mode: mode }),
      fetchServerMode: async () => {
        const settings = await getCompanionSettings();
        return settings.assistant_mode === "chief_of_staff"
          ? "chief_of_staff"
          : "life_companion";
      },
    });
  }

  return (
    <main
      className={[
        "relative min-h-dvh overflow-hidden transition-colors duration-700",
        isChief ? "bg-[#070d14] text-slate-100" : "bg-[#f7f3ea] text-stone-950",
      ].join(" ")}
    >
      <HomeNebulaBackground mode={mode} />

      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-[1500px] flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="mb-5 flex items-center justify-between gap-3">
          <Link
            href="/chat-v2"
            className={[
              "inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-semibold shadow-sm backdrop-blur transition active:scale-[0.98]",
              isChief
                ? "border-white/10 bg-white/[0.045] text-slate-300 hover:bg-white/[0.07] hover:text-white"
                : "border-white/75 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
            ].join(" ")}
          >
            <MessageCircle className="h-4 w-4" />
            Chat
          </Link>

          <div
            className={[
              "hidden rounded-full border px-4 py-2 text-[11px] font-bold uppercase tracking-[0.26em] sm:block",
              isChief
                ? "border-teal-200/15 bg-teal-200/[0.06] text-teal-100"
                : "border-white/75 bg-white/60 text-stone-500",
            ].join(" ")}
          >
            Calendar · Memory · Goals {contextWithName.status === "loading" ? "loading" : "live"}
          </div>
        </header>

        <section className="grid flex-1 gap-5 lg:grid-cols-[1.05fr_0.95fr]">
          <section className="flex min-h-0 flex-col">
            <div
              className={[
                "relative overflow-hidden rounded-[2.25rem] border p-5 shadow-2xl backdrop-blur-xl sm:p-7 lg:min-h-[calc(100dvh-8.75rem)]",
                isChief
                  ? "border-white/10 bg-white/[0.05] shadow-black/35"
                  : "border-white/80 bg-white/58 shadow-stone-200/60",
              ].join(" ")}
            >
              <div className="pointer-events-none absolute inset-0 opacity-70">
                <div
                  className={[
                    "absolute left-10 top-10 h-64 w-64 rounded-full blur-3xl",
                    isChief ? "bg-teal-400/10" : "bg-amber-300/18",
                  ].join(" ")}
                />
                <div
                  className={[
                    "absolute bottom-8 right-8 h-72 w-72 rounded-full blur-3xl",
                    isChief ? "bg-cyan-400/10" : "bg-pink-300/14",
                  ].join(" ")}
                />
              </div>

              <div className="relative">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <p
                      className={[
                        "text-[11px] font-bold uppercase tracking-[0.32em]",
                        isChief ? "text-teal-200/75" : "text-stone-400",
                      ].join(" ")}
                    >
                      {dayTime}
                    </p>
                    <h1 className="mt-5 max-w-3xl text-5xl font-semibold tracking-[-0.065em] sm:text-6xl lg:text-7xl">
                      {greeting || "Selamat datang"}, Syahid.
                    </h1>
                  </div>

                  <ModeToggle mode={mode} onChange={setMode} />
                </div>

                <div className="mt-8 max-w-2xl">
                  <p
                    className={[
                      "text-[11px] font-bold uppercase tracking-[0.24em]",
                      isChief ? "text-teal-100/70" : "text-stone-400",
                    ].join(" ")}
                  >
                    {copy.eyebrow}
                  </p>
                  <h2 className="mt-3 text-2xl font-semibold tracking-[-0.04em] sm:text-3xl">
                    {copy.title}
                  </h2>
                  <p
                    className={[
                      "mt-4 text-base leading-8 sm:text-lg",
                      isChief ? "text-slate-300" : "text-stone-600",
                    ].join(" ")}
                  >
                    {liveSummary}
                  </p>
                </div>

                <div
                  className={[
                    "mt-8 rounded-[2rem] border p-3 backdrop-blur-xl",
                    isChief
                      ? "border-white/10 bg-black/18"
                      : "border-white/75 bg-white/68",
                  ].join(" ")}
                >
                  <form onSubmit={submitHandoff}>
                    <textarea
                      value={handoffInput}
                      onChange={(event) => setHandoffInput(event.target.value)}
                      onKeyDown={(event) => {
                        if (event.key !== "Enter" || event.shiftKey) return;

                        const isMobile = window.matchMedia("(max-width: 640px)").matches;
                        if (isMobile) return;

                        event.preventDefault();
                        openChatWithHandoff(handoffInput, "home-composer");
                      }}
                      rows={3}
                      placeholder={copy.prompt}
                      className={[
                        "min-h-28 w-full resize-none rounded-[1.55rem] border px-4 py-4 text-sm leading-7 outline-none transition placeholder:text-current placeholder:opacity-65",
                        isChief
                          ? "border-white/10 bg-white/[0.045] text-slate-300 focus:border-teal-200/25 focus:bg-white/[0.06]"
                          : "border-stone-200/80 bg-white/64 text-stone-700 focus:border-stone-300 focus:bg-white/80",
                      ].join(" ")}
                    />

                    <span className={isChief ? "mt-2 block px-1 text-xs text-slate-500" : "mt-2 block px-1 text-xs text-stone-500"}>
                      {copy.summary}
                    </span>

                    <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
                      <div className="flex flex-wrap gap-2">
                        <HomeChip icon={<Sparkles className="h-3.5 w-3.5" />} label={copy.secondary} isChief={isChief} />
                        <HomeChip icon={<Mic className="h-3.5 w-3.5" />} label="Voice later" isChief={isChief} />
                      </div>

                      <button
                        type="submit"
                        className={[
                          "inline-flex h-11 items-center justify-center gap-2 rounded-full px-5 text-sm font-semibold shadow-sm transition active:scale-[0.98]",
                          isChief
                            ? "bg-teal-100 text-slate-950 hover:bg-white"
                            : "bg-stone-950 text-white hover:bg-stone-800",
                        ].join(" ")}
                      >
                        {handoffInput.trim() ? "Continue in chat" : copy.primary}
                        <ArrowRight className="h-4 w-4" />
                      </button>
                    </div>
                  </form>
                </div>

                <div className="mt-6 grid gap-3 sm:grid-cols-3">
                  <VitalSign
                    label="Calendar"
                    value={`${statusLabel(contextWithName.agendaStatus)} · ${contextWithName.todayAgenda?.length ?? 0} today`}
                    icon={<CalendarDays className="h-4 w-4" />}
                    isChief={isChief}
                  />
                  <VitalSign
                    label="Memory"
                    value={`${contextWithName.recentMemories?.length ?? 0} surfaced`}
                    icon={<Brain className="h-4 w-4" />}
                    isChief={isChief}
                  />
                  <VitalSign
                    label="Goals"
                    value={`${contextWithName.activeGoals?.length ?? 0} active`}
                    icon={<Target className="h-4 w-4" />}
                    isChief={isChief}
                  />
                </div>

                <ContextHealthStrip context={contextWithName} isChief={isChief} />
              </div>
            </div>
          </section>

          <aside className="grid min-h-0 gap-4 lg:h-[calc(100dvh-8.75rem)] lg:overflow-y-auto lg:overscroll-contain lg:pr-1 lg:[scrollbar-width:thin]">
            <HomePanel
              title={`$Quick starts`}
              badge={contextWithName.status === "loading" ? "Loading" : "Live"}
              icon={<Sparkles className="h-4 w-4" />}
              isChief={isChief}
            >
              <div className="grid gap-2">
                {offers.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => openChatWithHandoff(offerPrompt(item), `home-offer:${item}`)}
                    className={[
                      "flex items-center justify-between rounded-2xl border px-4 py-3 text-left text-sm transition",
                      isChief
                        ? "border-white/10 bg-white/[0.035] text-slate-300 hover:bg-white/[0.06]"
                        : "border-stone-200/75 bg-white/52 text-stone-600 hover:bg-white/75 hover:text-stone-950",
                    ].join(" ")}
                  >
                    {item}
                    <ArrowRight className="h-3.5 w-3.5 opacity-55" />
                  </button>
                ))}
              </div>
            </HomePanel>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1">
              <HomePanel
                title="Today’s agenda"
                badge={`Calendar · ${statusLabel(contextWithName.agendaStatus)}`}
                icon={<CalendarDays className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewList
                  items={contextWithName.todayAgenda || []}
                  empty="No agenda for today."
                  render={(item) => (
                    <PreviewLine
                      key={item.id || `${item.title}-${item.startAt}`}
                      title={agendaTitle(item)}
                      detail={agendaDetail(item)}
                      href={item.googleLink || undefined}
                    />
                  )}
                />
              </HomePanel>

              <HomePanel
                title="Upcoming reminders"
                badge={`Reminders · ${statusLabel(contextWithName.remindersStatus)}`}
                icon={<Bell className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewList
                  items={contextWithName.upcomingReminders || []}
                  empty="No upcoming reminders."
                  render={(item) => (
                    <PreviewLine
                      key={item.id || `${item.title}-${item.dueAt}`}
                      title={reminderTitle(item)}
                      detail={reminderDetail(item)}
                    />
                  )}
                />
              </HomePanel>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1">
              <HomePanel
                title="Daily brief"
                badge="Brief"
                icon={<MessageCircle className="h-4 w-4" />}
                isChief={isChief}
              >
                {contextWithName.briefingContent ? (
                  <PreviewLine
                    title="Today’s briefing"
                    detail={truncateText(contextWithName.briefingContent, 160)}
                    href={contextWithName.briefingConversationId ? `/chat-v2/${contextWithName.briefingConversationId}` : undefined}
                  />
                ) : (
                  <EmptyLine label={contextWithName.journaledToday ? "Journal signal is available today." : "No daily brief surfaced yet."} />
                )}
              </HomePanel>

              <HomePanel
                title="Active goals"
                badge="Goals"
                icon={<Target className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewList
                  items={contextWithName.activeGoals || []}
                  empty="No active goals surfaced."
                  render={(item) => (
                    <PreviewLine
                      key={item.id || item.title}
                      title={goalTitle(item)}
                      detail={goalDetail(item)}
                      href="/goals"
                    />
                  )}
                />
              </HomePanel>
            </div>

            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-1">
              <HomePanel
                title="Recent memories"
                badge="Memory"
                icon={<Brain className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewList
                  items={contextWithName.recentMemories || []}
                  empty="No recent memories surfaced."
                  render={(item) => (
                    <PreviewLine
                      key={item.id || item.content}
                      title={memoryTitle(item)}
                      detail={memoryDetail(item)}
                      href="/memories"
                    />
                  )}
                />
              </HomePanel>

              <HomePanel
                title="People who matter"
                badge="People"
                icon={<Users className="h-4 w-4" />}
                isChief={isChief}
              >
                <PreviewList
                  items={(contextWithName.people || []).slice(0, 5)}
                  empty="No people context surfaced."
                  render={(item) => (
                    <PreviewLine
                      key={item.id || item.name}
                      title={personTitle(item)}
                      detail={personDetail(item)}
                      href="/people"
                    />
                  )}
                />
              </HomePanel>
            </div>
          </aside>
        </section>
      </div>
    </main>
  );
}

function HomeNebulaBackground({ mode }: { mode: AssistantMode }) {
  const isChief = mode === "chief_of_staff";

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className={[
          "absolute inset-0 transition-opacity duration-700",
          isChief
            ? "bg-[radial-gradient(circle_at_20%_12%,rgba(45,212,191,0.13),transparent_30rem),radial-gradient(circle_at_78%_18%,rgba(56,189,248,0.10),transparent_34rem),radial-gradient(circle_at_48%_88%,rgba(20,184,166,0.08),transparent_30rem)]"
            : "bg-[radial-gradient(circle_at_18%_12%,rgba(251,191,36,0.16),transparent_30rem),radial-gradient(circle_at_82%_16%,rgba(45,212,191,0.12),transparent_34rem),radial-gradient(circle_at_70%_86%,rgba(244,114,182,0.11),transparent_30rem)]",
        ].join(" ")}
      />
      <div
        className={[
          "absolute inset-0 opacity-[0.05] [background-image:linear-gradient(rgba(120,113,108,0.45)_1px,transparent_1px),linear-gradient(90deg,rgba(120,113,108,0.35)_1px,transparent_1px)] [background-size:46px_46px]",
          isChief ? "mix-blend-screen" : "",
        ].join(" ")}
      />
      <div
        className={[
          "absolute left-1/2 top-1/2 h-[42rem] w-[42rem] -translate-x-1/2 -translate-y-1/2 rounded-full blur-3xl transition-colors duration-700",
          isChief ? "bg-teal-400/[0.035]" : "bg-white/35",
        ].join(" ")}
      />
    </div>
  );
}

function ModeToggle({
  mode,
  onChange,
}: {
  mode: AssistantMode;
  onChange: (mode: AssistantMode) => void;
}) {
  const isChief = mode === "chief_of_staff";

  return (
    <div
      className={[
        "inline-flex rounded-full border p-1 backdrop-blur",
        isChief ? "border-white/10 bg-white/[0.045]" : "border-white/75 bg-white/65",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => onChange("life_companion")}
        className={[
          "inline-flex h-9 items-center gap-2 rounded-full px-3 text-xs font-semibold transition",
          mode === "life_companion"
            ? isChief
              ? "bg-white text-slate-950"
              : "bg-stone-950 text-white"
            : isChief
              ? "text-slate-400 hover:text-white"
              : "text-stone-500 hover:text-stone-950",
        ].join(" ")}
      >
        <Heart className="h-3.5 w-3.5" />
        Life
      </button>
      <button
        type="button"
        onClick={() => onChange("chief_of_staff")}
        className={[
          "inline-flex h-9 items-center gap-2 rounded-full px-3 text-xs font-semibold transition",
          mode === "chief_of_staff"
            ? "bg-teal-100 text-slate-950"
            : isChief
              ? "text-slate-400 hover:text-white"
              : "text-stone-500 hover:text-stone-950",
        ].join(" ")}
      >
        <BriefcaseBusiness className="h-3.5 w-3.5" />
        Chief
      </button>
    </div>
  );
}

function HomeChip({
  icon,
  label,
  isChief,
}: {
  icon: ReactNode;
  label: string;
  isChief: boolean;
}) {
  return (
    <span
      className={[
        "inline-flex h-8 items-center gap-2 rounded-full border px-3 text-xs font-medium",
        isChief
          ? "border-white/10 bg-white/[0.035] text-slate-300"
          : "border-stone-200/75 bg-white/58 text-stone-600",
      ].join(" ")}
    >
      {icon}
      {label}
    </span>
  );
}

function VitalSign({
  label,
  value,
  icon,
  isChief,
}: {
  label: string;
  value: string;
  icon: ReactNode;
  isChief: boolean;
}) {
  return (
    <div
      className={[
        "rounded-2xl border p-4 backdrop-blur",
        isChief
          ? "border-white/10 bg-white/[0.04]"
          : "border-white/75 bg-white/58",
      ].join(" ")}
    >
      <div className="flex items-center justify-between gap-3">
        <p
          className={[
            "text-[10px] font-bold uppercase tracking-[0.22em]",
            isChief ? "text-slate-500" : "text-stone-400",
          ].join(" ")}
        >
          {label}
        </p>
        <span className={isChief ? "text-teal-100/80" : "text-stone-500"}>{icon}</span>
      </div>
      <p className="mt-3 flex items-center gap-2 text-sm font-semibold">
        <CircleDot className={isChief ? "h-3.5 w-3.5 text-teal-200" : "h-3.5 w-3.5 text-emerald-600"} />
        {value}
      </p>
    </div>
  );
}

function ContextHealthStrip({
  context,
  isChief,
}: {
  context: WorkspaceContext;
  isChief: boolean;
}) {
  const sources = context.sourceHealth || [];

  if (sources.length === 0) return null;

  return (
    <div
      className={[
        "mt-4 rounded-[1.5rem] border p-3 backdrop-blur",
        isChief
          ? "border-white/10 bg-black/12"
          : "border-white/75 bg-white/52",
      ].join(" ")}
    >
      <div className="mb-2 flex items-center justify-between gap-3 px-1">
        <p
          className={[
            "text-[10px] font-bold uppercase tracking-[0.22em]",
            isChief ? "text-teal-100/55" : "text-stone-400",
          ].join(" ")}
        >
          Live context health
        </p>
        <span className={isChief ? "text-[11px] text-slate-500" : "text-[11px] text-stone-500"}>
          {context.status === "loading" ? "Checking sources" : "Updated every 60s"}
        </span>
      </div>

      <div className="flex flex-wrap gap-2">
        {sources.map((source) => (
          <span
            key={source.id}
            title={source.detail}
            className={[
              "inline-flex min-h-8 items-center gap-2 rounded-full border px-3 py-1 text-[11px] font-semibold",
              healthStatusClass(source.status, isChief),
            ].join(" ")}
          >
            <span className={["h-1.5 w-1.5 rounded-full", healthStatusDotClass(source.status, isChief)].join(" ")} />
            {source.label}
            <span className="opacity-65">{healthStatusLabel(source.status)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

function HomePanel({
  title,
  badge,
  icon,
  isChief,
  children,
}: {
  title: string;
  badge: string;
  icon: ReactNode;
  isChief: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={[
        "rounded-[1.75rem] border p-4 shadow-xl backdrop-blur-xl",
        isChief
          ? "border-white/10 bg-white/[0.045] shadow-black/25"
          : "border-white/80 bg-white/58 shadow-stone-200/45",
      ].join(" ")}
    >
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p
            className={[
              "text-[10px] font-bold uppercase tracking-[0.22em]",
              isChief ? "text-teal-100/55" : "text-stone-400",
            ].join(" ")}
          >
            {badge}
          </p>
          <h3 className="mt-1 text-lg font-semibold tracking-[-0.035em]">{title}</h3>
        </div>
        <span
          className={[
            "grid h-9 w-9 shrink-0 place-items-center rounded-full",
            isChief ? "bg-teal-200/[0.07] text-teal-100" : "bg-white/70 text-stone-500",
          ].join(" ")}
        >
          {icon}
        </span>
      </div>
      <div className="grid gap-2">{children}</div>
    </section>
  );
}

function PreviewList<T>({
  items,
  empty,
  render,
}: {
  items: T[];
  empty: string;
  render: (item: T) => ReactNode;
}) {
  if (items.length === 0) return <EmptyLine label={empty} />;
  return <>{items.slice(0, 5).map(render)}</>;
}

function EmptyLine({ label }: { label: string }) {
  return (
    <div className="rounded-2xl border border-dashed border-current/15 bg-white/[0.025] px-3 py-4 text-sm opacity-65">
      {label}
    </div>
  );
}

function PreviewLine({
  title,
  detail,
  href,
}: {
  title: string;
  detail: string;
  href?: string | null;
}) {
  const content = (
    <>
      <p className="text-sm font-semibold leading-5">{title}</p>
      <p className="mt-1 text-xs leading-5 opacity-60">{detail}</p>
    </>
  );

  if (href) {
    return (
      <Link
        href={href}
        className="rounded-2xl border border-current/10 bg-white/[0.035] px-3 py-3 transition hover:bg-white/[0.08]"
      >
        {content}
      </Link>
    );
  }

  return (
    <div className="rounded-2xl border border-current/10 bg-white/[0.035] px-3 py-3">
      {content}
    </div>
  );
}
