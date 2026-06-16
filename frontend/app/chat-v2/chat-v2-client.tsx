"use client";

import Link from "next/link";
import {
  ArrowLeft,
  BriefcaseBusiness,
  CheckCircle2,
  CircleDot,
  Copy,
  Expand,
  FileText,
  Heart,
  ImageIcon,
  Loader2,
  Minimize2,
  Paperclip,
  Sparkles,
  X,
} from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useChatStreamSender } from "@/components/chat/use-chat-stream-sender";
import {
  getCompanionSettings,
  getIdentity,
  getTodayBriefing,
  getTodaysJournal,
  listConversations,
  listGoals,
  listMemories,
  listMessages,
  listPeople,
  patchCompanionSettings,
  uploadAttachment,
  type AttachmentMeta,
  type ChatStreamMeta,
  type Message,
} from "@/lib/api";
import {
  ASSISTANT_MODE_EVENT,
  changeAssistantMode,
  extractAssistantMode,
  extractAssistantName,
} from "./mode-events";
import type { WorkspaceContext } from "./workspace/types";
import { WorkspacePanel } from "./workspace/workspace-panel";
import { ChatV2CommandMenu } from "./chat-v2-command-menu";
import {
  loadTodayWorkspaceAgenda,
  loadUpcomingWorkspaceReminders,
} from "./workspace/load-live-context";


const ASSISTANT_NAME_CACHE_KEY = "app:assistant-name";
const EMPTY_INITIAL_MESSAGES: Message[] = [];

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

function writeCachedAssistantName(value: string | null): void {
  const cleaned = cleanAssistantName(value);
  if (typeof window === "undefined" || !cleaned) return;

  try {
    window.localStorage.setItem(ASSISTANT_NAME_CACHE_KEY, cleaned);
  } catch {}
}

type AssistantMode = "life_companion" | "chief_of_staff";

type LayoutMode = "split" | "expanded";

type LocalMessage =
  | Message
  | { id: string; role: "assistant"; content: string; pending: true; created_at?: string };

type ChatV2MessageAttachment = NonNullable<Message["attachments"]>[number];

function getModeCopy(mode: AssistantMode, assistantName: string | null) {
  const name = assistantName && assistantName.trim() ? assistantName.trim() : null;

  if (mode === "chief_of_staff") {
    return {
      eyebrow: "Calm executive cockpit",
      title: "Chief of Staff",
      description: `Structured, concise, and decision-oriented. ${
        name ?? "Your assistant"
      } helps prioritize, identify risks, and move execution forward.`,
      input: name
        ? `Ask ${name} to brief, prioritize, or structure next actions...`
        : "Ask for a brief, priorities, or next actions...",
      user: "Besok banyak agenda. Bantu aku prioritasin.",
      assistant:
        "Baik. Bottom line: kita pisahkan agenda menjadi keputusan, follow-up, dan deep work. Kirim daftar agendanya; aku susun prioritas, risiko, dan next action.",
    };
  }

  return {
    eyebrow: "Soft personal sanctuary",
    title: "Life Companion",
    description: `Warm, personal, and emotionally present. ${
      name ?? "Your assistant"
    } helps you reflect, remember, and navigate life with continuity.`,
    input: name ? `Cerita ke ${name}...` : "Cerita di sini...",
    user: "Aku capek hari ini, tapi pikiranku masih rame.",
    assistant:
      "Aku di sini. Kita pelan-pelan aja ya. Ceritain satu hal yang paling berat dulu, nanti aku bantu rapihin jadi langkah kecil.",
  };
}

function formatConversationTitle(
  conversationTitle: string | null | undefined,
  assistantName: string | null,
  isExpanded: boolean,
): string {
  const title = String(conversationTitle || "").trim();
  const name = cleanAssistantName(assistantName) || "your assistant";

  if (!title) return isExpanded ? "Expanded chat" : "Split assistant desk";
  if (title.startsWith("Main Chat -")) return `Main Chat - ${name}`;

  return title;
}

export function ChatV2Client({
  conversationId,
  initialMessages = EMPTY_INITIAL_MESSAGES,
  conversationTitle = null,
}: {
  conversationId?: string | null;
  initialMessages?: Message[];
  conversationTitle?: string | null;
}) {
  const [mode, setModeState] = useState<AssistantMode>("life_companion");
  const [modeReady, setModeReady] = useState(false);
  const [layout, setLayoutState] = useState<LayoutMode>("split");
  const [messages, setMessages] = useState<LocalMessage[]>(initialMessages);
  const [resolvedConversationTitle, setResolvedConversationTitle] = useState<string | null>(conversationTitle);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [streamMeta, setStreamMeta] = useState<ChatStreamMeta | null>(null);
  const [workspaceContext, setWorkspaceContext] = useState<WorkspaceContext>({
    status: "loading",
  });
  const [settingsAssistantName, setSettingsAssistantName] = useState<string | null>(() => readCachedAssistantName());
  const messagesScrollRef = useRef<HTMLDivElement | null>(null);

  const isChief = mode === "chief_of_staff";

  useLayoutEffect(() => {
    try {
      const savedMode = window.localStorage.getItem("aliyya.chatV2.mode");

      if (savedMode === "chief_of_staff" || savedMode === "life_companion") {
        setModeState(savedMode);
        setModeReady(true);
      }
    } catch {
      // The async settings loader below will still resolve the mode.
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function hydrateWorkspaceContext() {
      try {
        const [
          briefingResult,
          journalResult,
          goalsResult,
          identityResult,
          peopleResult,
          memoriesResult,
          agendaResult,
          remindersResult,
        ] = await Promise.allSettled([
          getTodayBriefing(),
          getTodaysJournal(),
          listGoals("all"),
          getIdentity(),
          listPeople(),
          listMemories(),
          loadTodayWorkspaceAgenda(),
          loadUpcomingWorkspaceReminders(),
        ]);

        if (cancelled) return;

        const briefing =
          briefingResult.status === "fulfilled" ? briefingResult.value : null;
        const journal =
          journalResult.status === "fulfilled" ? journalResult.value : null;
        const goals =
          goalsResult.status === "fulfilled" && Array.isArray(goalsResult.value)
            ? goalsResult.value
            : [];
        const identity =
          identityResult.status === "fulfilled" ? identityResult.value : null;
        const people =
          peopleResult.status === "fulfilled" && Array.isArray(peopleResult.value)
            ? peopleResult.value
            : [];
        const memories =
          memoriesResult.status === "fulfilled" && Array.isArray(memoriesResult.value)
            ? memoriesResult.value
            : [];
        const agenda =
          agendaResult.status === "fulfilled" && Array.isArray(agendaResult.value)
            ? agendaResult.value
            : [];
        const reminders =
          remindersResult.status === "fulfilled" && Array.isArray(remindersResult.value)
            ? remindersResult.value
            : [];

        const toWorkspaceGoal = (goal: (typeof goals)[number]) => ({
          id: typeof goal?.id === "string" ? goal.id : undefined,
          title: typeof goal?.title === "string" ? goal.title : undefined,
          status: typeof goal?.status === "string" ? goal.status : undefined,
        });

        setWorkspaceContext({
          status: "ready",
          briefingContent:
            typeof briefing?.content === "string" ? briefing.content : null,
          briefingOpenedAt:
            typeof briefing?.opened_at === "string" ? briefing.opened_at : null,
          briefingConversationId:
            typeof briefing?.conversation_id === "string"
              ? briefing.conversation_id
              : null,
          journaledToday: Boolean(journal?.entry),
          activeGoals: goals
            .filter((goal) => goal?.status === "active" || !goal?.status)
            .slice(0, 4)
            .map(toWorkspaceGoal),
          pausedGoals: goals
            .filter((goal) => goal?.status === "paused")
            .slice(0, 3)
            .map(toWorkspaceGoal),
          people: [...people]
            .sort(
              (a, b) =>
                (Number(b?.importance) || 0) - (Number(a?.importance) || 0),
            )
            .slice(0, 4)
            .map((person) => ({
              id: typeof person?.id === "string" ? person.id : undefined,
              name: typeof person?.name === "string" ? person.name : undefined,
              relationship:
                typeof person?.relationship === "string"
                  ? person.relationship
                  : null,
            })),
          recentMemories: [...memories]
            .sort((a, b) =>
              String(b?.created_at || "").localeCompare(String(a?.created_at || "")),
            )
            .slice(0, 3)
            .map((memory) => ({
              id: typeof memory?.id === "string" ? memory.id : undefined,
              content:
                typeof memory?.content === "string" ? memory.content : undefined,
              kind: typeof memory?.kind === "string" ? memory.kind : undefined,
              createdAt:
                typeof memory?.created_at === "string"
                  ? memory.created_at
                  : undefined,
            })),
          todayAgenda: agenda,
          upcomingReminders: reminders,
          agendaStatus: agendaResult.status === "fulfilled" ? "ready" : "error",
          remindersStatus:
            remindersResult.status === "fulfilled" ? "ready" : "error",
          assistantName:
            typeof identity?.profile?.assistant_name === "string"
              ? identity.profile.assistant_name
              : null,
        });
      } catch {
        if (!cancelled) {
          setWorkspaceContext({ status: "error" });
        }
      }
    }

    void hydrateWorkspaceContext();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function refreshLiveWorkspaceCards() {
      if (
        typeof document !== "undefined" &&
        document.visibilityState !== "visible"
      ) {
        return;
      }

      const [agendaResult, remindersResult] = await Promise.allSettled([
        loadTodayWorkspaceAgenda(),
        loadUpcomingWorkspaceReminders(),
      ]);

      if (cancelled) return;

      setWorkspaceContext((current) => ({
        ...current,
        todayAgenda:
          agendaResult.status === "fulfilled" ? agendaResult.value : current.todayAgenda,
        upcomingReminders:
          remindersResult.status === "fulfilled"
            ? remindersResult.value
            : current.upcomingReminders,
        agendaStatus: agendaResult.status === "fulfilled" ? "ready" : "error",
        remindersStatus:
          remindersResult.status === "fulfilled" ? "ready" : "error",
      }));
    }

    const interval = window.setInterval(() => {
      void refreshLiveWorkspaceCards();
    }, 60000);

    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        void refreshLiveWorkspaceCards();
      }
    }

    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function hydrateWorkspaceState() {
      let nextMode: AssistantMode = "life_companion";
      let nextName: string | null = null;

      try {
        const settings = await getCompanionSettings();
        nextMode =
          settings.assistant_mode === "chief_of_staff"
            ? "chief_of_staff"
            : "life_companion";
        nextName =
          typeof settings.assistant_name === "string" && settings.assistant_name.trim()
            ? settings.assistant_name.trim()
            : null;
      } catch {
        try {
          const savedMode = window.localStorage.getItem("aliyya.chatV2.mode");
          nextMode = savedMode === "chief_of_staff" ? "chief_of_staff" : "life_companion";
        } catch {
          nextMode = "life_companion";
        }
      }

      if (cancelled) return;

      setModeState(nextMode);
        setModeReady(true);
      if (nextName) {
        setSettingsAssistantName(nextName);
        writeCachedAssistantName(nextName);
      }

      try {
        window.localStorage.setItem("aliyya.chatV2.mode", nextMode);
        const savedLayout = window.localStorage.getItem("aliyya.chatV2.layout");
        const nextLayout: LayoutMode =
          savedLayout === "expanded" || savedLayout === "split" ? savedLayout : "split";
        setLayoutState(nextLayout);
      } catch {
        setLayoutState("split");
      }
    }

    void hydrateWorkspaceState();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    function onAssistantModeEvent(event: Event) {
      const detail = (event as CustomEvent<unknown>).detail;
      const eventMode = extractAssistantMode(detail);
      const eventName = extractAssistantName(detail);

      // Apply only — never broadcast from inside this listener. Dispatching
      // the event we are currently handling would synchronously recurse into
      // this listener until the call stack overflows.
      if (eventMode) {
        applyModeLocally(eventMode);
      }
      if (eventName) {
        setSettingsAssistantName(eventName);
      }
    }

    window.addEventListener(ASSISTANT_MODE_EVENT, onAssistantModeEvent);

    return () => {
      window.removeEventListener(ASSISTANT_MODE_EVENT, onAssistantModeEvent);
    };
  }, []);

  // Updates this surface only: React state + localStorage. Chat V2 never
  // dispatches the global event itself — the persistence layer (lib/api.ts on
  // successful settings save) and the stream sender are the app's
  // broadcasters, and this surface's listener applies whatever they announce.
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

  function setLayout(nextLayout: LayoutMode) {
    setLayoutState(nextLayout);

    try {
      window.localStorage.setItem("aliyya.chatV2.layout", nextLayout);
    } catch {}
  }

  const activeConversationId = conversationId ?? "";

  function scrollMessagesToBottom() {
    requestAnimationFrame(() => {
      const el = messagesScrollRef.current;
      if (!el) return;
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    });
  }

  async function refreshMessagesFromServer() {
    if (!activeConversationId) return;

    try {
      const latest = await listMessages(activeConversationId, { limit: 80 });
      setMessages(latest);
      scrollMessagesToBottom();
    } catch {}
  }

  const handleSend = useChatStreamSender({
    conversationId: activeConversationId,
    input,
    setInput,
    sending,
    setSending,
    messagesLength: messages.length,
    setMessages,
    setStreamMeta,
    markShouldStickToBottom: scrollMessagesToBottom,
  });

  useEffect(() => {
    const assistantMode = streamMeta?.assistant_mode;
    if (assistantMode !== "chief_of_staff" && assistantMode !== "life_companion") {
      return;
    }

    // Apply only. The stream sender (useChatStreamSender) already broadcasts
    // mode commands globally; re-broadcasting here duplicated the event.
    applyModeLocally(assistantMode);
  }, [streamMeta?.assistant_mode]);

  useEffect(() => {
    const nextName = cleanAssistantName(streamMeta?.assistant_name);
    if (!nextName) return;

    setSettingsAssistantName(nextName);
    writeCachedAssistantName(nextName);
  }, [streamMeta?.assistant_name]);

  useEffect(() => {
    setMessages(initialMessages);
  }, [initialMessages]);

  useEffect(() => {
    setResolvedConversationTitle(conversationTitle);
  }, [conversationTitle]);

  useEffect(() => {
    scrollMessagesToBottom();
  }, [messages]);

  useEffect(() => {
    if (!activeConversationId) return;

    let cancelled = false;

    async function hydrateConversationRoute() {
      const [messagesResult, conversationsResult] = await Promise.allSettled([
        listMessages(activeConversationId),
        listConversations(),
      ]);

      if (cancelled) return;

      if (messagesResult.status === "fulfilled") {
        setMessages(messagesResult.value);
      }

      if (conversationsResult.status === "fulfilled") {
        const activeConversation = conversationsResult.value.find(
          (conversation) => conversation.id === activeConversationId,
        );

        if (activeConversation) {
          setResolvedConversationTitle(activeConversation.title || null);
        }
      }

      requestAnimationFrame(() => {
        scrollMessagesToBottom();
      });
    }

    void hydrateConversationRoute();

    return () => {
      cancelled = true;
    };
  }, [activeConversationId]);

  useEffect(() => {
    if (!activeConversationId) return;

    let cancelled = false;

    async function refreshWhenIdle() {
      if (cancelled) return;
      if (sending) return;
      if (typeof document !== "undefined" && document.visibilityState !== "visible") return;

      await refreshMessagesFromServer();
    }

    const interval = window.setInterval(() => {
      void refreshWhenIdle();
    }, 15000);

    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        void refreshWhenIdle();
      }
    }

    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [activeConversationId, sending]);

  if (!modeReady) {
    return <ChatV2BootSplash />;
  }

  const isExpanded = layout === "expanded";
  // Name precedence mirrors the app's architecture: stream meta is the
  // freshest server-pushed value (in-chat renames), companion settings is the
  // authoritative store, identity remains a legacy fallback.
  const streamAssistantName = cleanAssistantName(streamMeta?.assistant_name);
  const identityAssistantName = cleanAssistantName(workspaceContext.assistantName);
  const assistantName =
    streamAssistantName ?? settingsAssistantName ?? identityAssistantName;
  const workspaceContextWithName: WorkspaceContext = {
    ...workspaceContext,
    assistantName,
  };

  function applyWorkspacePrompt(prompt: string) {
    const nextPrompt = prompt.replace(/\s+/g, " ").trim();
    if (!nextPrompt) return;

    setInput(nextPrompt);

    requestAnimationFrame(() => {
      const textarea = document.querySelector<HTMLTextAreaElement>("textarea");
      textarea?.focus();
    });
  }

  const copy = getModeCopy(mode, assistantName);

  return (
    <main
      className={[
        "relative min-h-dvh overflow-hidden transition-colors duration-700",
        isChief ? "bg-[#080d14] text-slate-100" : "bg-[#f7f3ea] text-stone-950",
      ].join(" ")}
    >
      <ModeBackground mode={mode} />

      <div className="relative z-10 mx-auto flex min-h-dvh w-full max-w-[1500px] flex-col px-4 py-5 sm:px-6 lg:px-8">
        <header className="mb-5 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ChatV2CommandMenu assistantName={assistantName} mode={mode} />
            <Link
              href="/chat-v2"
              className={[
                "inline-flex h-10 items-center gap-2 rounded-full border px-4 text-sm font-medium shadow-sm backdrop-blur transition active:scale-[0.98]",
                isChief
                  ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.07] hover:text-white"
                  : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
              ].join(" ")}
            >
              <ArrowLeft className="h-4 w-4" />
              Main chat
            </Link>
          </div>

          <div
            className={[
              "hidden rounded-full border px-4 py-2 text-[11px] font-semibold uppercase tracking-[0.26em] sm:block",
              isChief
                ? "border-teal-200/15 bg-teal-200/[0.06] text-teal-100"
                : "border-stone-200 bg-white/65 text-stone-500",
            ].join(" ")}
          >
            Companion Chat
          </div>
        </header>

        <section
          className={[
            "grid flex-1 gap-5 transition-all duration-700",
            isExpanded ? "grid-cols-1" : "grid-cols-1 xl:grid-cols-[0.82fr_1.18fr]",
          ].join(" ")}
        >
          {!isExpanded ? (
            <aside className="flex min-h-0 flex-col xl:h-[calc(100dvh-8.75rem)]">
              <div className="mb-5 shrink-0">
                <ModePill mode={mode} />
                <h1 className="mt-5 max-w-2xl text-5xl font-semibold tracking-[-0.06em] sm:text-6xl lg:text-7xl">
                  {copy.title}
                </h1>
                <p
                  className={[
                    "mt-5 max-w-xl text-base leading-8 sm:text-lg",
                    isChief ? "text-slate-300" : "text-stone-600",
                  ].join(" ")}
                >
                  {copy.description}
                </p>
              </div>

              <div className="shrink-0">
                <ModeToggle mode={mode} setMode={setMode} />
              </div>

              <div className="mt-5 min-h-0 flex-1 xl:overflow-y-auto xl:overscroll-contain xl:pb-2 xl:pr-1 xl:[scrollbar-width:thin]">
                <WorkspacePanel mode={mode} context={workspaceContextWithName} 
                  onPrompt={applyWorkspacePrompt}/>
              </div>
            </aside>
          ) : null}

          <section className="flex min-h-0 flex-col">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <p
                  className={[
                    "text-[11px] font-semibold uppercase tracking-[0.28em]",
                    isChief ? "text-teal-200/80" : "text-stone-400",
                  ].join(" ")}
                >
                  {copy.eyebrow}
                </p>
                <p
                  className={[
                    "mt-1 text-sm",
                    isChief ? "text-slate-400" : "text-stone-500",
                  ].join(" ")}
                >
                  {isExpanded ? "Focus chat active" : "Assistant desk active"}
                </p>
              </div>

              <div className="flex items-center gap-2">
                {isExpanded ? <ModeToggle mode={mode} setMode={setMode} compact /> : null}
                <button
                  type="button"
                  onClick={() => setLayout(isExpanded ? "split" : "expanded")}
                  className={[
                    "inline-flex h-10 items-center gap-2 rounded-full border px-3 text-sm font-medium shadow-sm backdrop-blur transition active:scale-[0.98]",
                    isChief
                      ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.07] hover:text-white"
                      : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
                  ].join(" ")}
                >
                  {isExpanded ? (
                    <>
                      <Minimize2 className="h-4 w-4" />
                      Split
                    </>
                  ) : (
                    <>
                      <Expand className="h-4 w-4" />
                      Expand
                    </>
                  )}
                </button>
              </div>
            </div>

            <ChatFrame
              mode={mode}
              assistantName={assistantName}
              isExpanded={isExpanded}
              messages={messages}
              conversationTitle={resolvedConversationTitle}
              input={input}
              sending={sending}
              canSend={Boolean(activeConversationId)}
              onInputChange={setInput}
              onSubmit={async (attachmentIds = []) => {
                await handleSend(attachmentIds);
                await refreshMessagesFromServer();
              }}
              messagesScrollRef={messagesScrollRef}
            />
          </section>
        </section>
      </div>
    </main>
  );
}


function ChatV2BootSplash() {
  return (
    <main className="relative min-h-dvh overflow-hidden bg-[#080d14] text-slate-100">
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_24%,rgba(45,212,191,0.13),transparent_28rem),radial-gradient(circle_at_18%_78%,rgba(96,165,250,0.07),transparent_32rem),radial-gradient(circle_at_82%_88%,rgba(180,130,58,0.04),transparent_26rem)]" />
        <div className="absolute inset-0 opacity-[0.04] [background-image:linear-gradient(rgba(148,163,184,0.30)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.24)_1px,transparent_1px)] [background-size:48px_48px]" />
      </div>
    </main>
  );
}

function ModeBackground({ mode }: { mode: AssistantMode }) {
  if (mode === "chief_of_staff") {
    return (
      <div aria-hidden="true" className="pointer-events-none absolute inset-0">
        <div className="absolute inset-0 bg-[#080d14]" />
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_24%,rgba(45,212,191,0.16),transparent_28rem),radial-gradient(circle_at_18%_78%,rgba(96,165,250,0.08),transparent_32rem),radial-gradient(circle_at_82%_88%,rgba(180,130,58,0.05),transparent_26rem)]" />
        <div className="absolute inset-0 opacity-[0.045] [background-image:linear-gradient(rgba(148,163,184,0.30)_1px,transparent_1px),linear-gradient(90deg,rgba(148,163,184,0.24)_1px,transparent_1px)] [background-size:48px_48px]" />
        <div className="absolute right-[-8%] top-[4%] h-[42rem] w-[42rem] rounded-full bg-teal-300/[0.08] blur-[120px]" />
        <div className="absolute bottom-[-20%] left-[-14%] h-[44rem] w-[44rem] rounded-full bg-blue-400/[0.05] blur-[150px]" />
      </div>
    );
  }

  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div className="absolute inset-0 bg-[#f7f3ea]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_18%_18%,rgba(244,194,194,0.42),transparent_28rem),radial-gradient(circle_at_76%_18%,rgba(206,220,183,0.34),transparent_30rem),radial-gradient(circle_at_48%_86%,rgba(235,224,166,0.36),transparent_34rem)]" />
      <div className="absolute bottom-[-18%] left-[10%] h-[34rem] w-[34rem] rounded-full bg-lime-200/20 blur-[120px]" />
      <div className="absolute right-[-10%] top-[20%] h-[34rem] w-[34rem] rounded-full bg-rose-200/20 blur-[130px]" />
    </div>
  );
}

function ModePill({ mode }: { mode: AssistantMode }) {
  const isChief = mode === "chief_of_staff";
  const Icon = isChief ? BriefcaseBusiness : Sparkles;

  return (
    <div
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-[11px] font-semibold uppercase tracking-[0.18em] shadow-sm backdrop-blur",
        isChief
          ? "border-teal-200/15 bg-teal-200/[0.06] text-teal-100"
          : "border-stone-200 bg-white/65 text-stone-500",
      ].join(" ")}
    >
      <Icon className="h-3.5 w-3.5" />
      {isChief ? "Calm executive cockpit" : "Soft personal sanctuary"}
    </div>
  );
}

function ModeToggle({
  mode,
  setMode,
  compact = false,
}: {
  mode: AssistantMode;
  setMode: (mode: AssistantMode) => void;
  compact?: boolean;
}) {
  const isChief = mode === "chief_of_staff";

  return (
    <div
      className={[
        "inline-flex rounded-full border p-1 shadow-sm backdrop-blur",
        isChief
          ? "border-white/10 bg-black/20"
          : "border-stone-200 bg-white/65",
      ].join(" ")}
    >
      <button
        type="button"
        onClick={() => setMode("life_companion")}
        className={[
          "rounded-full px-4 py-2 text-sm font-semibold transition",
          compact ? "px-3 py-1.5 text-xs" : "",
          !isChief
            ? "bg-white text-stone-950 shadow-sm"
            : "text-slate-400 hover:text-white",
        ].join(" ")}
      >
        Life
      </button>
      <button
        type="button"
        onClick={() => setMode("chief_of_staff")}
        className={[
          "rounded-full px-4 py-2 text-sm font-semibold transition",
          compact ? "px-3 py-1.5 text-xs" : "",
          isChief
            ? "border border-teal-200/20 bg-slate-800/80 text-white shadow-sm"
            : "text-stone-500 hover:text-stone-950",
        ].join(" ")}
      >
        Chief
      </button>
    </div>
  );
}

type ChatV2PendingUpload =
  | { kind: "uploading"; clientId: string; filename: string; fileKind: "image" | "document" }
  | { kind: "done"; clientId: string; meta: AttachmentMeta }
  | { kind: "error"; clientId: string; filename: string; error: string };

const CHAT_V2_ATTACHMENT_ACCEPT = "image/jpeg,image/png,image/gif,image/webp,application/pdf";

function chatV2FileKind(mimeType: string): "image" | "document" {
  return mimeType.startsWith("image/") ? "image" : "document";
}

function ChatV2Composer({
  mode,
  value,
  onChange,
  onSubmit,
  disabled,
  placeholder,
}: {
  mode: AssistantMode;
  value: string;
  onChange: (value: string) => void;
  onSubmit: (attachmentIds?: string[]) => void;
  disabled: boolean;
  placeholder: string;
}) {
  const isChief = mode === "chief_of_staff";
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const [pendingUploads, setPendingUploads] = useState<ChatV2PendingUpload[]>([]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 176)}px`;
  }, [value]);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;

    for (const file of Array.from(files).slice(0, 10)) {
      const clientId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const fileKind = chatV2FileKind(file.type);

      setPendingUploads((current) => [
        ...current,
        {
          kind: "uploading",
          clientId,
          filename: file.name,
          fileKind,
        },
      ]);

      try {
        const meta = await uploadAttachment(file);

        setPendingUploads((current) =>
          current.map((item) =>
            item.clientId === clientId ? { kind: "done", clientId, meta } : item,
          ),
        );
      } catch (error) {
        setPendingUploads((current) =>
          current.map((item) =>
            item.clientId === clientId
              ? {
                  kind: "error",
                  clientId,
                  filename: file.name,
                  error: error instanceof Error ? error.message : "Upload failed",
                }
              : item,
          ),
        );
      }
    }
  }

  function removeUpload(clientId: string) {
    setPendingUploads((current) => current.filter((item) => item.clientId !== clientId));
  }

  function submit() {
    const attachmentIds = pendingUploads
      .filter((item): item is Extract<ChatV2PendingUpload, { kind: "done" }> => item.kind === "done")
      .map((item) => item.meta.id);
    const hasText = value.trim().length > 0;
    const hasAttachments = attachmentIds.length > 0;
    const hasUploading = pendingUploads.some((item) => item.kind === "uploading");

    if (disabled || hasUploading || (!hasText && !hasAttachments)) return;

    onSubmit(attachmentIds);
    setPendingUploads([]);
  }

  const uploadingCount = pendingUploads.filter((item) => item.kind === "uploading").length;
  const canSend =
    !disabled &&
    uploadingCount === 0 &&
    (value.trim().length > 0 || pendingUploads.some((item) => item.kind === "done"));

  return (
    <div className="shrink-0 px-4 pb-4 pt-3 sm:px-5">
      <div className="mx-auto w-full max-w-4xl">
        {pendingUploads.length > 0 ? (
          <div className="mb-2 flex flex-wrap gap-2 px-1">
            {pendingUploads.map((item) => (
              <ChatV2AttachmentChip
                key={item.clientId}
                item={item}
                isChief={isChief}
                onRemove={() => removeUpload(item.clientId)}
              />
            ))}
          </div>
        ) : null}

        <div
          className={[
            "flex items-end gap-2 rounded-[1.75rem] border px-2.5 py-2 shadow-sm backdrop-blur-xl transition",
            isChief
              ? "border-white/10 bg-white/[0.055] text-slate-100 shadow-black/20 focus-within:border-white/20 focus-within:bg-white/[0.075]"
              : "border-white/75 bg-white/64 text-stone-950 shadow-stone-200/50 focus-within:border-white/90 focus-within:bg-white/82",
          ].join(" ")}
        >
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            aria-label="Attach file"
            className={[
              "grid h-10 w-10 shrink-0 place-items-center rounded-full transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-35",
              isChief
                ? "text-slate-400 hover:bg-white/[0.07] hover:text-white"
                : "text-stone-500 hover:bg-stone-900/[0.06] hover:text-stone-950",
            ].join(" ")}
          >
            <Paperclip className="h-4 w-4" />
          </button>

          <input
            ref={fileInputRef}
            type="file"
            accept={CHAT_V2_ATTACHMENT_ACCEPT}
            multiple
            className="hidden"
            onChange={(event) => {
              void handleFiles(event.target.files);
              event.target.value = "";
            }}
          />

          <textarea
            ref={textareaRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={(event) => {
              if (event.key !== "Enter" || event.shiftKey) return;

              const isMobile = window.matchMedia("(max-width: 640px)").matches;
              if (isMobile) return;

              event.preventDefault();
              submit();
            }}
            rows={1}
            disabled={disabled}
            placeholder={placeholder}
            enterKeyHint="send"
            autoCapitalize="sentences"
            autoCorrect="on"
            spellCheck
            className={[
              "min-h-10 max-h-44 flex-1 resize-none bg-transparent px-1 py-2 text-base leading-7 outline-none placeholder:opacity-60 sm:text-[16px]",
              isChief
                ? "text-slate-100 placeholder:text-slate-500"
                : "text-stone-950 placeholder:text-stone-500",
            ].join(" ")}
          />

          <button
            type="button"
            onClick={submit}
            disabled={!canSend}
            aria-label="Send message"
            className={[
              "grid h-10 w-10 shrink-0 place-items-center rounded-full transition active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-30",
              isChief
                ? "bg-slate-100 text-slate-950 hover:bg-white"
                : "bg-stone-950 text-white hover:bg-stone-800",
            ].join(" ")}
          >
            {uploadingCount > 0 ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ArrowLeft className="h-4 w-4 rotate-90" />
            )}
          </button>
        </div>

        <div className="mt-2 flex items-center justify-center gap-2 text-[11px]">
          {uploadingCount > 0 ? (
            <span className={isChief ? "text-slate-500" : "text-stone-500"}>
              Uploading {uploadingCount} file{uploadingCount > 1 ? "s" : ""}…
            </span>
          ) : (
            <span className={isChief ? "text-slate-600" : "text-stone-400"}>
              Attach images or PDFs · Shift + Enter for newline
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

function ChatV2AttachmentChip({
  item,
  isChief,
  onRemove,
}: {
  item: ChatV2PendingUpload;
  isChief: boolean;
  onRemove: () => void;
}) {
  const isImage =
    item.kind === "done"
      ? item.meta.kind === "image"
      : item.kind === "uploading"
        ? item.fileKind === "image"
        : false;
  const label =
    item.kind === "done"
      ? item.meta.original_filename
      : item.kind === "uploading"
        ? item.filename
        : item.error;

  return (
    <div
      className={[
        "group flex max-w-[16rem] items-center gap-2 rounded-full border px-3 py-1.5 text-xs backdrop-blur",
        item.kind === "error"
          ? "border-red-300/40 bg-red-50/70 text-red-700"
          : isChief
            ? "border-white/10 bg-white/[0.055] text-slate-300"
            : "border-white/75 bg-white/70 text-stone-600",
      ].join(" ")}
    >
      {item.kind === "uploading" ? (
        <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin opacity-70" />
      ) : isImage ? (
        <ImageIcon className="h-3.5 w-3.5 shrink-0 opacity-70" />
      ) : (
        <FileText className="h-3.5 w-3.5 shrink-0 opacity-70" />
      )}

      <span className="min-w-0 truncate">{label}</span>

      <button
        type="button"
        onClick={onRemove}
        aria-label="Remove attachment"
        className="grid h-5 w-5 shrink-0 place-items-center rounded-full opacity-60 transition hover:bg-black/5 hover:opacity-100"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}


function getMessageAttachments(message: LocalMessage): ChatV2MessageAttachment[] {
  if ("attachments" in message && Array.isArray(message.attachments)) {
    return message.attachments;
  }

  return [];
}

function isPendingAssistantMessage(message: LocalMessage): boolean {
  return message.role === "assistant" && "pending" in message && message.pending === true;
}

function formatAttachmentSize(sizeBytes?: number | null): string | null {
  if (!sizeBytes || sizeBytes <= 0) return null;
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  if (sizeBytes < 1024 * 1024) return `${Math.round(sizeBytes / 1024)} KB`;
  return `${(sizeBytes / (1024 * 1024)).toFixed(1)} MB`;
}

function ChatV2MessageBubble({
  message,
  isChief,
}: {
  message: LocalMessage;
  isChief: boolean;
}) {
  const [copied, setCopied] = useState(false);
  const isUser = message.role === "user";
  const attachments = getMessageAttachments(message);
  const pending = isPendingAssistantMessage(message);
  const isAttachmentOnlyPlaceholder =
    attachments.length > 0 && message.content.trim() === "(shared an attachment)";
  const displayContent = isAttachmentOnlyPlaceholder ? "" : message.content;
  const copyText = [
    displayContent.trim(),
    ...attachments.map((attachment) => attachment.original_filename).filter(Boolean),
  ]
    .filter(Boolean)
    .join("\n");

  async function copyMessage() {
    if (!copyText || typeof navigator === "undefined" || !navigator.clipboard) return;

    try {
      await navigator.clipboard.writeText(copyText);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch {
      setCopied(false);
    }
  }

  if (!isUser && pending && !displayContent.trim()) {
    return (
      <div className="max-w-[min(92%,52rem)] rounded-[1.6rem] rounded-bl-md border px-4 py-4 text-sm leading-7 sm:px-5">
        <div
          className={[
            "inline-flex items-center gap-2",
            isChief ? "text-slate-300" : "text-stone-500",
          ].join(" ")}
        >
          <ChatV2TypingDots />
          <span className="text-xs">Thinking</span>
        </div>
      </div>
    );
  }

  return (
    <div
      className={[
        "group relative",
        isUser
          ? "ml-auto max-w-[min(88%,48rem)] rounded-[1.6rem] rounded-br-md px-4 py-3 text-sm leading-7 sm:px-5"
          : "max-w-[min(92%,52rem)] rounded-[1.6rem] rounded-bl-md border px-4 py-4 text-sm leading-7 sm:px-5",
        isUser
          ? isChief
            ? "bg-slate-100 text-slate-950"
            : "bg-stone-900 text-stone-50"
          : isChief
            ? "border-white/10 bg-white/[0.055] text-slate-200"
            : "border-white/80 bg-white/72 text-stone-800",
      ].join(" ")}
    >
      {displayContent.trim() ? (
        <span className="block whitespace-pre-wrap break-words [overflow-wrap:anywhere]">
          {displayContent}
        </span>
      ) : null}

      <ChatV2MessageAttachments
        attachments={attachments}
        isChief={isChief}
        isUser={isUser}
        flushTop={!displayContent.trim()}
      />

      {copyText ? (
        <button
          type="button"
          onClick={copyMessage}
          className={[
            "mt-3 inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-[11px] font-medium opacity-70 transition hover:opacity-100 sm:opacity-0 sm:group-hover:opacity-100",
            isUser
              ? isChief
                ? "border-slate-300/70 bg-slate-950/[0.04] text-slate-700"
                : "border-white/15 bg-white/10 text-white/80 hover:text-white"
              : isChief
                ? "border-white/10 bg-white/[0.035] text-slate-400 hover:text-slate-100"
                : "border-stone-200/80 bg-white/45 text-stone-500 hover:text-stone-800",
          ].join(" ")}
          aria-label={copied ? "Message copied" : "Copy message"}
          title={copied ? "Copied" : "Copy"}
        >
          {copied ? <CheckCircle2 className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
          {copied ? "Copied" : "Copy"}
        </button>
      ) : null}
    </div>
  );
}

function ChatV2MessageAttachments({
  attachments,
  isChief,
  isUser,
  flushTop = false,
}: {
  attachments: ChatV2MessageAttachment[];
  isChief: boolean;
  isUser: boolean;
  flushTop?: boolean;
}) {
  if (attachments.length === 0) return null;

  return (
    <div className={[flushTop ? "mt-0" : "mt-3", "flex flex-wrap gap-2"].join(" ")}>
      {attachments.map((attachment) => {
        const isImage =
          attachment.kind === "image" || attachment.media_type?.startsWith("image/");
        const sizeLabel = formatAttachmentSize(attachment.size_bytes);

        return (
          <div
            key={attachment.id}
            className={[
              "inline-flex max-w-[18rem] items-center gap-2 rounded-2xl border px-3 py-2 text-xs backdrop-blur",
              isUser
                ? isChief
                  ? "border-slate-300/70 bg-slate-950/[0.04] text-slate-700"
                  : "border-white/15 bg-white/10 text-white/85"
                : isChief
                  ? "border-white/10 bg-white/[0.04] text-slate-300"
                  : "border-stone-200/80 bg-white/55 text-stone-600",
            ].join(" ")}
          >
            {isImage ? (
              <ImageIcon className="h-4 w-4 shrink-0 opacity-75" />
            ) : (
              <FileText className="h-4 w-4 shrink-0 opacity-75" />
            )}
            <span className="min-w-0">
              <span className="block truncate font-medium">
                {attachment.original_filename || "Attachment"}
              </span>
              <span className="block truncate opacity-65">
                {isImage ? "Image" : "Document"}
                {sizeLabel ? ` · ${sizeLabel}` : ""}
              </span>
            </span>
          </div>
        );
      })}
    </div>
  );
}

function ChatV2TypingDots() {
  return (
    <span className="inline-flex items-center gap-1" aria-hidden="true">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-45 [animation-delay:-0.2s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-55 [animation-delay:-0.1s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-current opacity-65" />
    </span>
  );
}


function ChatFrame({
  mode,
  assistantName,
  isExpanded,
  messages,
  conversationTitle,
  input,
  sending,
  canSend,
  onInputChange,
  onSubmit,
  messagesScrollRef,
}: {
  mode: AssistantMode;
  assistantName: string | null;
  isExpanded: boolean;
  messages: LocalMessage[];
  conversationTitle?: string | null;
  input: string;
  sending: boolean;
  canSend: boolean;
  onInputChange: (value: string) => void;
  onSubmit: (attachmentIds?: string[]) => void;
  messagesScrollRef: { current: HTMLDivElement | null };
}) {
  const isChief = mode === "chief_of_staff";
  const copy = getModeCopy(mode, assistantName);

  return (
    <div
      className={[
        "flex h-[calc(100dvh-8.75rem)] min-h-[520px] flex-col overflow-hidden rounded-[2rem] border shadow-2xl backdrop-blur-xl transition-all duration-700",
        isExpanded ? "mx-auto w-full max-w-5xl" : "w-full",
        isChief
          ? "border-teal-100/20 bg-[#0b141d]/82 shadow-black/35"
          : "border-white/80 bg-white/62 shadow-stone-200/60",
      ].join(" ")}
    >
      <div
        className={[
          "flex items-center justify-between border-b px-5 py-4",
          isChief ? "border-white/10" : "border-stone-200/70",
        ].join(" ")}
      >
        <div>
          <p
            className={[
              "text-[11px] font-semibold uppercase tracking-[0.28em]",
              isChief ? "text-teal-200/80" : "text-stone-400",
            ].join(" ")}
          >
            Live workspace
          </p>
          <p className={isChief ? "mt-1 text-sm text-slate-400" : "mt-1 text-sm text-stone-500"}>
            {formatConversationTitle(conversationTitle, assistantName, isExpanded)}
          </p>
        </div>

        <div
          className={[
            "grid h-12 w-12 place-items-center rounded-full border",
            isChief
              ? "border-teal-200/15 bg-teal-200/[0.06] shadow-[0_0_24px_rgba(45,212,191,0.20)]"
              : "border-stone-200 bg-white/70",
          ].join(" ")}
        >
          {isChief ? <CircleDot className="h-5 w-5 text-teal-100" /> : <Heart className="h-5 w-5 text-stone-500" />}
        </div>
      </div>

      <div ref={messagesScrollRef} className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-5 py-6 pr-3 scroll-smooth [scrollbar-width:thin]">
        {(messages.length > 0 ? messages : null)?.map((message) => (
          <ChatV2MessageBubble
            key={message.id}
            message={message}
            isChief={isChief}
          />
        ))}

        {messages.length === 0 ? (
          <>
            <div
              className={[
                "ml-auto max-w-[min(88%,48rem)] rounded-[1.6rem] rounded-br-md px-4 py-3 text-sm leading-7 sm:px-5",
                isChief ? "bg-slate-100 text-slate-950" : "bg-stone-900 text-stone-50",
              ].join(" ")}
            >
              {copy.user}
            </div>

            <div
              className={[
                "max-w-[86%] rounded-3xl border px-5 py-4 text-sm leading-7",
                isChief
                  ? "border-white/10 bg-white/[0.055] text-slate-200"
                  : "border-white/80 bg-white/72 text-stone-800",
              ].join(" ")}
            >
              {copy.assistant}
            </div>
          </>
        ) : null}

        <div className="grid gap-3 pt-4">
          {(isChief
            ? ["Brief me for today", "Prioritize my next actions", "Find risks and blockers"]
            : ["Help me reflect", "Write a gentle journal", "Remember this moment"]
          ).map((item) => (
            <button
              key={item}
              type="button"
              className={[
                "flex items-center gap-3 rounded-2xl border px-4 py-3 text-left text-sm transition",
                isChief
                  ? "border-teal-100/10 bg-black/12 text-slate-300 hover:bg-white/[0.055]"
                  : "border-stone-200/70 bg-white/45 text-stone-600 hover:bg-white/65",
              ].join(" ")}
            >
              <CheckCircle2 className={isChief ? "h-4 w-4 text-teal-200/70" : "h-4 w-4 text-stone-400"} />
              {item}
            </button>
          ))}
        </div>
      </div>

      <ChatV2Composer
        mode={mode}
        value={input}
        onChange={onInputChange}
        onSubmit={onSubmit}
        disabled={!canSend || sending}
        placeholder={canSend ? copy.input : "No conversation is available yet."}
      />
    </div>
  );
}
