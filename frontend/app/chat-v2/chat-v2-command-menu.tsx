"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  CalendarDays,
  Fingerprint,
  Heart,
  LogOut,
  Menu,
  MessageSquare,
  Palette,
  Plus,
  Search,
  Settings,
  ShieldCheck,
  Sparkles,
  Target,
  User,
  Users,
  Wand2,
  X,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  createConversation,
  listConversations,
  listStyleProfiles,
  type Conversation,
  type StyleProfile,
} from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { clearKnownAppSnapshots } from "@/lib/snapshot-cache";
import { cn } from "@/lib/utils";

type AssistantMode = "life_companion" | "chief_of_staff";

type LauncherItem = {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
  group: "Life OS" | "Customize";
};

const LAUNCHER_ITEMS: LauncherItem[] = [
  {
    href: "/journal",
    label: "Journal",
    description: "Mood, energy, stress, and quick daily reflection.",
    icon: Heart,
    group: "Life OS",
  },
  {
    href: "/goals",
    label: "Goals",
    description: "Active goals, suggestions, and follow-up proposals.",
    icon: Target,
    group: "Life OS",
  },
  {
    href: "/calendar",
    label: "Calendar",
    description: "Events, reminders, sync status, and schedule gaps.",
    icon: CalendarDays,
    group: "Life OS",
  },
  {
    href: "/people",
    label: "People",
    description: "Family, friends, colleagues, and important contacts.",
    icon: Users,
    group: "Life OS",
  },
  {
    href: "/identity",
    label: "Identity",
    description: "Your grounding profile, timezone, context, and preferences.",
    icon: User,
    group: "Life OS",
  },
  {
    href: "/memories",
    label: "Memories",
    description: "Review, edit, archive, and consolidate memory.",
    icon: Sparkles,
    group: "Life OS",
  },
  {
    href: "/settings/companion",
    label: "Companion Mode",
    description: "Working mode, relationship tone, and assistant name.",
    icon: Wand2,
    group: "Customize",
  },
  {
    href: "/settings/avatar-mode",
    label: "Avatar Mode",
    description: "Visual presence and avatar behavior.",
    icon: Palette,
    group: "Customize",
  },
  {
    href: "/settings/style-profiles",
    label: "Style Profiles",
    description: "Conversation styles from chat examples or presets.",
    icon: Fingerprint,
    group: "Customize",
  },
  {
    href: "/settings/security",
    label: "Security",
    description: "PIN, calendar access, and protected memory actions.",
    icon: ShieldCheck,
    group: "Customize",
  },
  {
    href: "/settings",
    label: "Settings",
    description: "All preferences and app configuration.",
    icon: Settings,
    group: "Customize",
  },
];

function formatConversationDate(value: string | null | undefined): string {
  if (!value) return "";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";

  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function cleanAssistantName(value: string | null | undefined): string {
  return value?.trim() || "your assistant";
}

type ConversationGroup =
  | "Today"
  | "Yesterday"
  | "Previous 7 days"
  | "Older";

const CONVERSATION_GROUP_ORDER: ConversationGroup[] = [
  "Today",
  "Yesterday",
  "Previous 7 days",
  "Older",
];

function isMainConversation(conversation: Conversation): boolean {
  return conversation.title.trim().toLowerCase().startsWith("main chat");
}

function getConversationGroup(
  value: string | null | undefined,
): ConversationGroup {
  if (!value) return "Older";

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Older";

  const now = new Date();

  const todayUtc = Date.UTC(
    now.getFullYear(),
    now.getMonth(),
    now.getDate(),
  );

  const conversationUtc = Date.UTC(
    date.getFullYear(),
    date.getMonth(),
    date.getDate(),
  );

  const daysAgo = Math.floor(
    (todayUtc - conversationUtc) / 86_400_000,
  );

  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo <= 7) return "Previous 7 days";

  return "Older";
}

export function ChatV2CommandMenu({
  assistantName,
  mode,
  currentConversationId,
}: {
  assistantName: string | null;
  mode: AssistantMode;
  currentConversationId: string | null;
}) {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [open, setOpen] = useState(false);
  const [chatsOpen, setChatsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [chatQuery, setChatQuery] = useState("");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [styleProfiles, setStyleProfiles] = useState<StyleProfile[]>([]);
  const [loading, setLoading] = useState(false);
  const [chatLoading, setChatLoading] = useState(false);
  const [creating, setCreating] = useState(false);

  const isChief = mode === "chief_of_staff";
  const displayName = cleanAssistantName(assistantName);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const isLauncherShortcut =
        (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";

      if (!isLauncherShortcut) return;

      event.preventDefault();
      setOpen((value) => !value);
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  useEffect(() => {
    if (!open) return;

    let cancelled = false;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    requestAnimationFrame(() => inputRef.current?.focus());

    async function loadLauncherData() {
      setLoading(true);

      try {
        const [conversationResult, styleResult] = await Promise.allSettled([
          listConversations(),
          listStyleProfiles(),
        ]);

        if (cancelled) return;

        if (conversationResult.status === "fulfilled") {
          setConversations(conversationResult.value);
        }

        if (styleResult.status === "fulfilled") {
          setStyleProfiles(styleResult.value.slice(0, 6));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void loadLauncherData();

    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    window.addEventListener("keydown", onEscape);

    return () => {
      cancelled = true;
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onEscape);
    };
  }, [open]);

  useEffect(() => {
    if (!chatsOpen) return;

    let cancelled = false;
    const previousOverflow = document.body.style.overflow;

    document.body.style.overflow = "hidden";
    setChatLoading(true);

    void listConversations()
      .then((items) => {
        if (!cancelled) {
          setConversations(items);
        }
      })
      .finally(() => {
        if (!cancelled) {
          setChatLoading(false);
        }
      });

    function onEscape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setChatsOpen(false);
      }
    }

    window.addEventListener("keydown", onEscape);

    return () => {
      cancelled = true;
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onEscape);
    };
  }, [chatsOpen]);

  const filteredConversations = useMemo(() => {
    const needle = chatQuery.trim().toLowerCase();

    if (!needle) return conversations;

    return conversations.filter((conversation) =>
      conversation.title.toLowerCase().includes(needle),
    );
  }, [chatQuery, conversations]);

  const mainConversation = useMemo(
    () =>
      filteredConversations.find((conversation) =>
        isMainConversation(conversation),
      ) ?? null,
    [filteredConversations],
  );

  const groupedConversations = useMemo(() => {
    const result: Record<ConversationGroup, Conversation[]> = {
      Today: [],
      Yesterday: [],
      "Previous 7 days": [],
      Older: [],
    };

    for (const conversation of filteredConversations) {
      if (isMainConversation(conversation)) continue;

      result[
        getConversationGroup(
          conversation.updated_at || conversation.created_at,
        )
      ].push(conversation);
    }

    return result;
  }, [filteredConversations]);

  const filteredItems = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return LAUNCHER_ITEMS;

    return LAUNCHER_ITEMS.filter((item) =>
      `${item.label} ${item.description} ${item.group}`
        .toLowerCase()
        .includes(needle),
    );
  }, [query]);

  const groupedItems = useMemo(
    () => ({
      "Life OS": filteredItems.filter((item) => item.group === "Life OS"),
      Customize: filteredItems.filter((item) => item.group === "Customize"),
    }),
    [filteredItems],
  );

  async function startNewChat(styleProfileId: string | null = null) {
    if (creating) return;

    setCreating(true);

    try {
      const conversation = await createConversation("New chat", styleProfileId);
      setOpen(false);
      setChatsOpen(false);
      router.push(`/chat-v2/${conversation.id}`);
    } finally {
      setCreating(false);
    }
  }

  async function signOut() {
    clearKnownAppSnapshots();

    const supabase = createClient();
    await supabase.auth.signOut();

    setOpen(false);
    router.push("/login");
    router.refresh();
  }

  return (
    <>
      <div className="inline-flex items-center gap-2">
        <button
          type="button"
          onClick={() => void startNewChat(null)}
          disabled={creating}
          aria-label={creating ? "Starting new chat" : "Start new chat"}
          className={cn(
            "inline-flex h-10 items-center gap-2 rounded-full border px-3 text-sm font-medium shadow-sm backdrop-blur transition active:scale-[0.98] disabled:cursor-wait disabled:opacity-60",
            isChief
              ? "border-teal-200/15 bg-teal-200/[0.07] text-teal-50 hover:bg-teal-200/[0.10]"
              : "border-stone-900 bg-stone-950 text-white hover:bg-stone-800",
          )}
        >
          <Plus className="h-4 w-4" />
          <span className="hidden sm:inline">
            {creating ? "Starting…" : "New chat"}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setChatsOpen(true)}
          aria-label="Open conversations"
          className={cn(
            "inline-flex h-10 items-center gap-2 rounded-full border px-3 text-sm font-medium shadow-sm backdrop-blur transition active:scale-[0.98]",
            isChief
              ? "border-white/10 bg-white/[0.04] text-slate-300 hover:bg-white/[0.07] hover:text-white"
              : "border-stone-200 bg-white/70 text-stone-600 hover:bg-white hover:text-stone-950",
          )}
        >
          <MessageSquare className="h-4 w-4" />
          <span className="hidden sm:inline">Chats</span>
        </button>
      </div>

      {chatsOpen ? (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label="Close conversations"
            className="absolute inset-0 bg-slate-950/30 backdrop-blur-sm"
            onClick={() => setChatsOpen(false)}
          />

          <aside
            aria-label="Conversations"
            className={cn(
              "absolute bottom-0 left-0 top-0 flex w-[min(92vw,24rem)] flex-col border-r p-4 shadow-2xl backdrop-blur-2xl",
              isChief
                ? "border-white/10 bg-[#0b141d]/96 text-slate-100 shadow-black/45"
                : "border-white/75 bg-[#fbf8f0]/96 text-stone-950 shadow-stone-900/20",
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p
                  className={cn(
                    "text-[10px] font-semibold uppercase tracking-[0.24em]",
                    isChief ? "text-teal-200/75" : "text-stone-400",
                  )}
                >
                  Conversations
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-[-0.03em]">
                  Your chats
                </h2>
              </div>

              <button
                type="button"
                onClick={() => setChatsOpen(false)}
                aria-label="Close conversations"
                className={cn(
                  "grid h-9 w-9 place-items-center rounded-full transition",
                  isChief
                    ? "text-slate-400 hover:bg-white/[0.07] hover:text-white"
                    : "text-stone-500 hover:bg-stone-900/[0.06] hover:text-stone-950",
                )}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <button
              type="button"
              onClick={() => void startNewChat(null)}
              disabled={creating}
              className={cn(
                "mt-4 flex w-full items-center gap-3 rounded-2xl border px-3 py-3 text-left transition active:scale-[0.99] disabled:opacity-60",
                isChief
                  ? "border-teal-200/15 bg-teal-200/[0.07] text-teal-50 hover:bg-teal-200/[0.10]"
                  : "border-stone-900 bg-stone-950 text-white hover:bg-stone-800",
              )}
            >
              <span
                className={cn(
                  "grid h-9 w-9 shrink-0 place-items-center rounded-full",
                  isChief
                    ? "bg-teal-100 text-slate-950"
                    : "bg-white text-stone-950",
                )}
              >
                <Plus className="h-4 w-4" />
              </span>

              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold">
                  {creating ? "Starting…" : "New chat"}
                </span>
                <span
                  className={cn(
                    "block text-[11px]",
                    isChief ? "text-teal-100/65" : "text-white/65",
                  )}
                >
                  Start a clean conversation
                </span>
              </span>
            </button>

            <div
              className={cn(
                "mt-3 flex items-center gap-2 rounded-2xl border px-3 py-2.5",
                isChief
                  ? "border-white/10 bg-black/20"
                  : "border-stone-200/80 bg-white/65",
              )}
            >
              <Search
                className={cn(
                  "h-4 w-4 shrink-0",
                  isChief ? "text-slate-500" : "text-stone-400",
                )}
              />
              <input
                value={chatQuery}
                onChange={(event) => setChatQuery(event.target.value)}
                placeholder="Search conversations"
                className={cn(
                  "min-w-0 flex-1 bg-transparent text-sm outline-none",
                  isChief
                    ? "text-slate-100 placeholder:text-slate-500"
                    : "text-stone-950 placeholder:text-stone-400",
                )}
              />
            </div>

            <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1 [scrollbar-width:thin]">
              {chatLoading ? (
                <p
                  className={cn(
                    "px-2 py-4 text-sm",
                    isChief ? "text-slate-500" : "text-stone-400",
                  )}
                >
                  Loading conversations…
                </p>
              ) : null}

              {!chatLoading && mainConversation ? (
                <div className="mb-4">
                  <p
                    className={cn(
                      "mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.22em]",
                      isChief ? "text-slate-500" : "text-stone-400",
                    )}
                  >
                    Pinned
                  </p>

                  <ConversationDrawerLink
                    conversation={mainConversation}
                    active={
                      mainConversation.id === currentConversationId
                    }
                    isChief={isChief}
                    onClick={() => setChatsOpen(false)}
                  />
                </div>
              ) : null}

              {!chatLoading
                ? CONVERSATION_GROUP_ORDER.map((group) => {
                    const items = groupedConversations[group];

                    if (items.length === 0) return null;

                    return (
                      <section key={group} className="mb-4">
                        <p
                          className={cn(
                            "mb-2 px-2 text-[10px] font-semibold uppercase tracking-[0.22em]",
                            isChief
                              ? "text-slate-500"
                              : "text-stone-400",
                          )}
                        >
                          {group}
                        </p>

                        <div className="space-y-1.5">
                          {items.map((conversation) => (
                            <ConversationDrawerLink
                              key={conversation.id}
                              conversation={conversation}
                              active={
                                conversation.id === currentConversationId
                              }
                              isChief={isChief}
                              onClick={() => setChatsOpen(false)}
                            />
                          ))}
                        </div>
                      </section>
                    );
                  })
                : null}

              {!chatLoading &&
              !mainConversation &&
              CONVERSATION_GROUP_ORDER.every(
                (group) => groupedConversations[group].length === 0,
              ) ? (
                <p
                  className={cn(
                    "rounded-2xl border px-3 py-4 text-sm",
                    isChief
                      ? "border-white/10 bg-white/[0.025] text-slate-500"
                      : "border-stone-200/70 bg-white/45 text-stone-500",
                  )}
                >
                  No conversations found.
                </p>
              ) : null}
            </div>

            <div
              className={cn(
                "mt-3 border-t pt-3",
                isChief ? "border-white/10" : "border-stone-200/70",
              )}
            >
              <button
                type="button"
                onClick={() => {
                  setChatsOpen(false);
                  window.setTimeout(() => setOpen(true), 0);
                }}
                className={cn(
                  "flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition",
                  isChief
                    ? "text-slate-400 hover:bg-white/[0.055] hover:text-white"
                    : "text-stone-500 hover:bg-stone-900/[0.06] hover:text-stone-950",
                )}
              >
                <Menu className="h-4 w-4" />
                Assistant OS
              </button>
            </div>
          </aside>
        </div>
      ) : null}

      {open ? (
        <div className="fixed inset-0 z-50">
          <button
            type="button"
            aria-label="Close assistant menu"
            className="absolute inset-0 bg-slate-950/30 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          />

          <section
            role="dialog"
            aria-modal="true"
            aria-label="Assistant menu"
            className={cn(
              "absolute bottom-0 left-0 right-0 max-h-[88dvh] overflow-hidden rounded-t-[2rem] border p-3 shadow-2xl backdrop-blur-2xl sm:bottom-auto sm:left-6 sm:right-auto sm:top-6 sm:w-[30rem] sm:rounded-[2rem]",
              isChief
                ? "border-white/10 bg-[#0b141d]/92 text-slate-100 shadow-black/40"
                : "border-white/75 bg-[#fbf8f0]/90 text-stone-950 shadow-stone-900/18",
            )}
          >
            <div className="flex items-start justify-between gap-3 px-2 pb-3 pt-1">
              <div>
                <p
                  className={cn(
                    "text-[11px] font-semibold uppercase tracking-[0.24em]",
                    isChief ? "text-teal-200/80" : "text-stone-400",
                  )}
                >
                  Assistant OS
                </p>
                <h2 className="mt-1 text-xl font-semibold tracking-[-0.03em]">
                  {displayName} menu
                </h2>
                <p
                  className={cn(
                    "mt-1 text-xs leading-5",
                    isChief ? "text-slate-400" : "text-stone-500",
                  )}
                >
                  Jump anywhere, start a chat, or tune how the assistant works.
                </p>
              </div>

              <button
                type="button"
                onClick={() => setOpen(false)}
                aria-label="Close menu"
                className={cn(
                  "grid h-9 w-9 shrink-0 place-items-center rounded-full transition",
                  isChief
                    ? "text-slate-400 hover:bg-white/[0.07] hover:text-white"
                    : "text-stone-500 hover:bg-stone-900/[0.06] hover:text-stone-950",
                )}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            <div
              className={cn(
                "flex items-center gap-2 rounded-2xl border px-3 py-2",
                isChief
                  ? "border-white/10 bg-black/20"
                  : "border-white/80 bg-white/65",
              )}
            >
              <Search
                className={cn(
                  "h-4 w-4",
                  isChief ? "text-slate-500" : "text-stone-400",
                )}
              />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search Journal, Goals, Calendar, Settings…"
                className={cn(
                  "min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:opacity-65",
                  isChief
                    ? "text-slate-100 placeholder:text-slate-500"
                    : "text-stone-950 placeholder:text-stone-500",
                )}
              />
              <span
                className={cn(
                  "hidden rounded-lg border px-1.5 py-0.5 text-[10px] font-medium sm:inline",
                  isChief
                    ? "border-white/10 text-slate-500"
                    : "border-stone-200 text-stone-400",
                )}
              >
                ⌘K
              </span>
            </div>

            <div className="mt-3 max-h-[calc(88dvh-10.5rem)] overflow-y-auto pr-1 [scrollbar-width:thin]">
              <button
                type="button"
                onClick={() => void startNewChat(null)}
                disabled={creating}
                className={cn(
                  "flex w-full items-center gap-3 rounded-2xl border px-4 py-3 text-left transition active:scale-[0.99] disabled:opacity-60",
                  isChief
                    ? "border-teal-200/15 bg-teal-200/[0.07] text-teal-50 hover:bg-teal-200/[0.10]"
                    : "border-stone-200 bg-stone-950 text-white shadow-lg shadow-stone-900/15 hover:bg-stone-800",
                )}
              >
                <span
                  className={cn(
                    "grid h-9 w-9 place-items-center rounded-full",
                    isChief ? "bg-teal-100 text-slate-950" : "bg-white text-stone-950",
                  )}
                >
                  <Plus className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold">
                    {creating ? "Starting chat…" : "New chat"}
                  </span>
                  <span
                    className={cn(
                      "block text-xs",
                      isChief ? "text-teal-100/70" : "text-white/70",
                    )}
                  >
                    Start clean, then choose a style if needed.
                  </span>
                </span>
              </button>

              {styleProfiles.length > 0 ? (
                <div className="mt-3">
                  <p
                    className={cn(
                      "mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.22em]",
                      isChief ? "text-slate-500" : "text-stone-400",
                    )}
                  >
                    Start with style
                  </p>
                  <div className="grid gap-2 sm:grid-cols-2">
                    {styleProfiles.map((profile) => (
                      <button
                        key={profile.id}
                        type="button"
                        onClick={() => void startNewChat(profile.id)}
                        disabled={creating}
                        className={cn(
                          "rounded-2xl border px-3 py-2 text-left text-xs transition disabled:opacity-60",
                          isChief
                            ? "border-white/10 bg-white/[0.035] text-slate-300 hover:bg-white/[0.06]"
                            : "border-stone-200/80 bg-white/60 text-stone-600 hover:bg-white",
                        )}
                      >
                        <span className="block truncate font-medium">
                          {profile.profile_name}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              ) : null}

              <LauncherSection title="Life OS" isChief={isChief}>
                {groupedItems["Life OS"].map((item) => (
                  <LauncherLink
                    key={item.href}
                    item={item}
                    isChief={isChief}
                    onClick={() => setOpen(false)}
                  />
                ))}
              </LauncherSection>

              <LauncherSection title="Customize" isChief={isChief}>
                {groupedItems.Customize.map((item) => (
                  <LauncherLink
                    key={item.href}
                    item={item}
                    isChief={isChief}
                    onClick={() => setOpen(false)}
                  />
                ))}
              </LauncherSection>

              <LauncherSection
                title={loading ? "Recent chats loading…" : "Recent chats"}
                isChief={isChief}
              >
                {conversations.length > 0 ? (
                  conversations.slice(0, 7).map((conversation) => (
                    <Link
                      key={conversation.id}
                      href={`/chat-v2/${conversation.id}`}
                      onClick={() => setOpen(false)}
                      className={cn(
                        "flex items-center gap-3 rounded-2xl border px-3 py-2.5 transition",
                        isChief
                          ? "border-white/10 bg-white/[0.025] text-slate-300 hover:bg-white/[0.055]"
                          : "border-stone-200/70 bg-white/45 text-stone-700 hover:bg-white/75",
                      )}
                    >
                      <MessageSquare className="h-4 w-4 shrink-0 opacity-65" />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium">
                          {conversation.title || "Untitled"}
                        </span>
                        <span
                          className={cn(
                            "block text-[11px]",
                            isChief ? "text-slate-500" : "text-stone-400",
                          )}
                        >
                          {formatConversationDate(conversation.updated_at)}
                        </span>
                      </span>
                    </Link>
                  ))
                ) : (
                  <p
                    className={cn(
                      "rounded-2xl border px-3 py-3 text-xs",
                      isChief
                        ? "border-white/10 bg-white/[0.025] text-slate-500"
                        : "border-stone-200/70 bg-white/45 text-stone-500",
                    )}
                  >
                    {loading ? "Loading…" : "No recent chats yet."}
                  </p>
                )}
              </LauncherSection>

              <div
                className={cn(
                  "mt-3 border-t pt-3",
                  isChief ? "border-white/10" : "border-stone-200/70",
                )}
              >
                <button
                  type="button"
                  onClick={() => void signOut()}
                  className={cn(
                    "flex w-full items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition",
                    isChief
                      ? "text-slate-400 hover:bg-white/[0.055] hover:text-white"
                      : "text-stone-500 hover:bg-stone-900/[0.06] hover:text-stone-950",
                  )}
                >
                  <LogOut className="h-4 w-4" />
                  Sign out
                </button>
              </div>
            </div>
          </section>
        </div>
      ) : null}
    </>
  );
}

function ConversationDrawerLink({
  conversation,
  active,
  isChief,
  onClick,
}: {
  conversation: Conversation;
  active: boolean;
  isChief: boolean;
  onClick: () => void;
}) {
  return (
    <Link
      href={`/chat-v2/${conversation.id}`}
      onClick={onClick}
      aria-current={active ? "page" : undefined}
      className={cn(
        "flex items-center gap-3 rounded-2xl border px-3 py-2.5 transition",
        active
          ? isChief
            ? "border-teal-200/20 bg-teal-200/[0.09] text-teal-50"
            : "border-stone-300 bg-white text-stone-950 shadow-sm"
          : isChief
            ? "border-transparent text-slate-400 hover:border-white/10 hover:bg-white/[0.045] hover:text-slate-100"
            : "border-transparent text-stone-600 hover:border-stone-200/70 hover:bg-white/65 hover:text-stone-950",
      )}
    >
      <MessageSquare className="h-4 w-4 shrink-0 opacity-60" />

      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">
          {conversation.title || "Untitled"}
        </span>
        <span
          className={cn(
            "mt-0.5 block text-[11px]",
            isChief ? "text-slate-600" : "text-stone-400",
          )}
        >
          {formatConversationDate(
            conversation.updated_at || conversation.created_at,
          )}
        </span>
      </span>

      {active ? (
        <span
          className={cn(
            "h-2 w-2 shrink-0 rounded-full",
            isChief ? "bg-teal-200" : "bg-stone-900",
          )}
          aria-hidden="true"
        />
      ) : null}
    </Link>
  );
}

function LauncherSection({
  title,
  isChief,
  children,
}: {
  title: string;
  isChief: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="mt-4">
      <p
        className={cn(
          "mb-2 px-1 text-[10px] font-semibold uppercase tracking-[0.22em]",
          isChief ? "text-slate-500" : "text-stone-400",
        )}
      >
        {title}
      </p>
      <div className="grid gap-2">{children}</div>
    </section>
  );
}

function LauncherLink({
  item,
  isChief,
  onClick,
}: {
  item: LauncherItem;
  isChief: boolean;
  onClick: () => void;
}) {
  const Icon = item.icon;

  return (
    <Link
      href={item.href}
      onClick={onClick}
      className={cn(
        "flex items-center gap-3 rounded-2xl border px-3 py-2.5 transition",
        isChief
          ? "border-white/10 bg-white/[0.025] text-slate-300 hover:bg-white/[0.055] hover:text-white"
          : "border-stone-200/70 bg-white/45 text-stone-700 hover:bg-white/75 hover:text-stone-950",
      )}
    >
      <span
        className={cn(
          "grid h-9 w-9 shrink-0 place-items-center rounded-2xl",
          isChief
            ? "bg-teal-200/[0.07] text-teal-100"
            : "bg-stone-100 text-stone-500",
        )}
      >
        <Icon className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{item.label}</span>
        <span
          className={cn(
            "mt-0.5 block truncate text-xs",
            isChief ? "text-slate-500" : "text-stone-500",
          )}
        >
          {item.description}
        </span>
      </span>
    </Link>
  );
}
