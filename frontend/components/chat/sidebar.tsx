"use client";

import Link from "next/link";
import { useRouter, useParams } from "next/navigation";
import {
  Heart,
  LogOut,
  Menu,
  MessageSquare,
  Plus,
  Sparkles,
  Target,
  Trash2,
  User,
  Users,
  X,
} from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import {
  type Conversation,
  createConversation,
  deleteConversation,
  getTodaysJournal,
  listConversations,
} from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";

// Group conversations by relative time, like ChatGPT / Claude.ai
type ConvoGroup = { label: string; conversations: Conversation[] };

function groupConversations(convos: Conversation[]): ConvoGroup[] {
  const now = Date.now();
  const ONE_DAY = 86_400_000;

  const buckets: { [k: string]: Conversation[] } = {
    Today: [],
    Yesterday: [],
    "Previous 7 days": [],
    "Previous 30 days": [],
    Older: [],
  };

  for (const c of convos) {
    const age = now - new Date(c.updated_at).getTime();
    if (age < ONE_DAY) buckets.Today.push(c);
    else if (age < 2 * ONE_DAY) buckets.Yesterday.push(c);
    else if (age < 7 * ONE_DAY) buckets["Previous 7 days"].push(c);
    else if (age < 30 * ONE_DAY) buckets["Previous 30 days"].push(c);
    else buckets.Older.push(c);
  }

  return Object.entries(buckets)
    .filter(([, items]) => items.length > 0)
    .map(([label, conversations]) => ({ label, conversations }));
}

export function Sidebar() {
  const router = useRouter();
  const params = useParams<{ id?: string }>();
  const activeId = params?.id;
  const qc = useQueryClient();

  const [open, setOpen] = useState(false);

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });

  const { data: today } = useQuery({
    queryKey: ["journal", "today"],
    queryFn: getTodaysJournal,
  });
  const journaledToday = today?.entry != null;

  const groups = useMemo(() => groupConversations(conversations), [conversations]);

  useEffect(() => {
    setOpen(false);
  }, [activeId]);

  useEffect(() => {
    if (open) {
      const prev = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      return () => {
        document.body.style.overflow = prev;
      };
    }
  }, [open]);

  const createMut = useMutation({
    mutationFn: () => createConversation(),
    onMutate: async () => {
      const optimistic: Conversation = {
        id: `temp-${Date.now()}`,
        title: "New chat",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      await qc.cancelQueries({ queryKey: ["conversations"] });
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) => [
        optimistic,
        ...old,
      ]);
      return { optimistic };
    },
    onSuccess: (real, _vars, ctx) => {
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.map((c) => (c.id === ctx?.optimistic.id ? real : c)),
      );
      setOpen(false);
      router.push(`/chat/${real.id}`);
    },
    onError: (_e, _v, ctx) => {
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.filter((c) => c.id !== ctx?.optimistic.id),
      );
    },
  });

  const deleteMut = useMutation({
    mutationFn: (id: string) => deleteConversation(id),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: ["conversations"] });
      const prev = qc.getQueryData<Conversation[]>(["conversations"]);
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.filter((c) => c.id !== id),
      );
      return { prev };
    },
    onError: (_e, _id, ctx) => {
      if (ctx?.prev) qc.setQueryData(["conversations"], ctx.prev);
    },
  });

  function handleDelete(id: string, e: React.MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!confirm("Delete this conversation?")) return;
    deleteMut.mutate(id);
    if (activeId === id) router.push("/chat");
  }

  async function handleSignOut() {
    const supabase = createClient();
    await supabase.auth.signOut();
    router.push("/login");
    router.refresh();
  }

  const sidebarBody = (
    <>
      {/* Brand */}
      <div className="shrink-0 px-4 pt-4 pb-3 flex items-center gap-2">
        <div className="h-7 w-7 rounded-lg bg-accent grid place-items-center shadow-sm">
          <Sparkles className="h-3.5 w-3.5 text-on-accent" strokeWidth={2.5} />
        </div>
        <span className="text-sm font-semibold text-fg tracking-tighter">
          Assistant
        </span>
        <button
          onClick={() => setOpen(false)}
          className="ml-auto md:hidden h-9 w-9 grid place-items-center rounded-lg text-fg-muted hover:bg-fg/5"
          aria-label="Close menu"
        >
          <X className="h-5 w-5" />
        </button>
      </div>

      {/* New chat */}
      <div className="shrink-0 px-3 pb-3">
        <button
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending}
          className="w-full flex items-center gap-2 rounded-xl bg-accent text-on-accent px-3 py-2.5 text-sm font-medium hover:bg-accent-hover transition-all hover:shadow-lg hover:shadow-accent/20 active:scale-[0.98] disabled:opacity-60"
        >
          <Plus className="h-4 w-4" strokeWidth={2.5} />
          New chat
        </button>
      </div>

      {/* History header */}
      {!isLoading && conversations.length > 0 && (
        <div className="shrink-0 px-4 pb-1.5">
          <p className="text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">
            Chat History
          </p>
        </div>
      )}

      {/* Conversations — flex-1 + min-h-0 lets this scroll independently */}
      <div className="flex-1 min-h-0 overflow-y-auto scroll-smooth-mobile px-2">
        {isLoading ? (
          <>
            <Skeleton className="h-8 mx-1 mb-1" />
            <Skeleton className="h-8 mx-1 mb-1 w-3/4" />
            <Skeleton className="h-8 mx-1 mb-1 w-2/3" />
          </>
        ) : conversations.length === 0 ? (
          <div className="px-2 py-3 text-center">
            <MessageSquare className="h-5 w-5 text-fg-subtle mx-auto mb-1.5 opacity-50" />
            <p className="text-xs text-fg-subtle">No conversations yet</p>
          </div>
        ) : (
          groups.map((g) => (
            <div key={g.label} className="mb-2">
              <p className="px-2.5 pt-2 pb-1 text-[10px] font-medium uppercase tracking-wide text-fg-subtle">
                {g.label}
              </p>
              {g.conversations.map((c) => (
                <Link
                  key={c.id}
                  href={`/chat/${c.id}`}
                  className={cn(
                    "group flex items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-sm mb-0.5 transition-all",
                    activeId === c.id
                      ? "bg-accent-soft text-fg font-medium"
                      : "text-fg-soft active:bg-fg/10 md:hover:bg-fg/5",
                  )}
                >
                  <span className="truncate flex-1 min-w-0">{c.title || "Untitled"}</span>
                  <button
                    onClick={(e) => handleDelete(c.id, e)}
                    className="opacity-100 md:opacity-0 md:group-hover:opacity-100 h-7 w-7 grid place-items-center text-fg-subtle hover:text-danger transition-opacity"
                    aria-label="Delete conversation"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </Link>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Footer — shrink-0 keeps it at the bottom and not eating list space */}
      <div className="shrink-0 px-3 py-3 border-t border-border space-y-0.5 pb-safe">
        <NavLink
          href="/journal"
          icon={<Heart className="h-4 w-4" />}
          label="Journal"
          showDot={today != null && !journaledToday}
        />
        <NavLink href="/goals" icon={<Target className="h-4 w-4" />} label="Goals" />
        <NavLink href="/people" icon={<Users className="h-4 w-4" />} label="People" />
        <NavLink href="/identity" icon={<User className="h-4 w-4" />} label="Identity" />
        <NavLink href="/memories" icon={<Sparkles className="h-4 w-4" />} label="Memories" />
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-fg-soft active:bg-fg/10 md:hover:bg-fg/5 hover:text-fg transition-colors"
        >
          <LogOut className="h-4 w-4 text-fg-muted" />
          Sign out
        </button>
      </div>
    </>
  );

  return (
    <>
      {/* Mobile topbar */}
      <div className="md:hidden fixed top-0 left-0 right-0 z-30 glass border-b border-border pt-safe">
        <div className="flex items-center gap-2 px-3 py-2">
          <button
            onClick={() => setOpen(true)}
            className="h-10 w-10 grid place-items-center rounded-lg text-fg active:bg-fg/10"
            aria-label="Open menu"
          >
            <Menu className="h-5 w-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="h-6 w-6 rounded-md bg-accent grid place-items-center">
              <Sparkles className="h-3 w-3 text-on-accent" strokeWidth={2.5} />
            </div>
            <span className="text-sm font-semibold text-fg tracking-tighter">
              Assistant
            </span>
          </div>
        </div>
      </div>

      {/* Mobile drawer */}
      {open && (
        <>
          <div
            className="md:hidden fixed inset-0 z-40 bg-black/40 drawer-backdrop-enter"
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <aside
            className="md:hidden glass-strong fixed left-0 top-0 bottom-0 z-50 w-[85vw] max-w-[300px] flex flex-col drawer-enter"
            role="dialog"
            aria-label="Navigation"
          >
            {sidebarBody}
          </aside>
        </>
      )}

      {/* Desktop sidebar — explicit height accounting for m-2 (= 0.5rem each side) */}
      <aside className="hidden md:flex glass-strong w-64 shrink-0 flex-col h-[calc(100dvh-1rem)] sticky top-2 m-2 mr-0 rounded-2xl overflow-hidden">
        {sidebarBody}
      </aside>
    </>
  );
}

function NavLink({
  href,
  icon,
  label,
  showDot,
}: {
  href: string;
  icon: React.ReactNode;
  label: string;
  showDot?: boolean;
}) {
  return (
    <Link
      href={href}
      className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm text-fg-soft active:bg-fg/10 md:hover:bg-fg/5 hover:text-fg transition-colors"
    >
      <span className="text-fg-muted">{icon}</span>
      <span className="flex-1">{label}</span>
      {showDot && (
        <span
          className="h-1.5 w-1.5 rounded-full bg-accent shadow-sm shadow-accent/40"
          aria-label="needs attention"
        />
      )}
    </Link>
  );
}
