"use client";

import Link from "next/link";
import { useRouter, useParams } from "next/navigation";
import { Heart, LogOut, Plus, Sparkles, Trash2, User, MessageSquare } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
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

export function Sidebar() {
  const router = useRouter();
  const params = useParams<{ id?: string }>();
  const activeId = params?.id;
  const qc = useQueryClient();

  const { data: conversations = [], isLoading } = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });

  const { data: today } = useQuery({
    queryKey: ["journal", "today"],
    queryFn: getTodaysJournal,
  });
  const journaledToday = today?.entry != null;

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

  return (
    <aside className="glass-strong w-64 shrink-0 flex flex-col h-full m-2 mr-0 rounded-2xl overflow-hidden">
      <div className="px-4 pt-4 pb-3 flex items-center gap-2">
        <div className="h-7 w-7 rounded-lg bg-accent grid place-items-center shadow-sm">
          <Sparkles className="h-3.5 w-3.5 text-on-accent" strokeWidth={2.5} />
        </div>
        <span className="text-sm font-semibold text-fg tracking-tighter">Assistant</span>
      </div>

      <div className="px-3 pb-3">
        <button
          onClick={() => createMut.mutate()}
          disabled={createMut.isPending}
          className="w-full flex items-center gap-2 rounded-xl bg-accent text-on-accent px-3 py-2 text-sm font-medium hover:bg-accent-hover transition-all hover:shadow-lg hover:shadow-accent/20 active:scale-[0.98] disabled:opacity-60"
        >
          <Plus className="h-4 w-4" strokeWidth={2.5} />
          New chat
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-2">
        {isLoading ? (
          <>
            <Skeleton className="h-7 mx-1 mb-1" />
            <Skeleton className="h-7 mx-1 mb-1 w-3/4" />
            <Skeleton className="h-7 mx-1 mb-1 w-2/3" />
          </>
        ) : conversations.length === 0 ? (
          <div className="px-2 py-3 text-center">
            <MessageSquare className="h-5 w-5 text-fg-subtle mx-auto mb-1.5 opacity-50" />
            <p className="text-xs text-fg-subtle">No conversations yet</p>
          </div>
        ) : (
          conversations.map((c) => (
            <Link
              key={c.id}
              href={`/chat/${c.id}`}
              className={cn(
                "group flex items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-sm mb-0.5 transition-all",
                activeId === c.id
                  ? "bg-accent-soft text-fg font-medium"
                  : "text-fg-soft hover:bg-fg/5",
              )}
            >
              <span className="truncate">{c.title || "Untitled"}</span>
              <button
                onClick={(e) => handleDelete(c.id, e)}
                className="opacity-0 group-hover:opacity-100 text-fg-subtle hover:text-danger transition-opacity"
                aria-label="Delete conversation"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </button>
            </Link>
          ))
        )}
      </div>

      <div className="px-3 py-3 border-t border-border space-y-0.5">
        <NavLink
          href="/journal"
          icon={<Heart className="h-4 w-4" />}
          label="Journal"
          showDot={today != null && !journaledToday}
        />
        <NavLink href="/identity" icon={<User className="h-4 w-4" />} label="Identity" />
        <NavLink href="/memories" icon={<Sparkles className="h-4 w-4" />} label="Memories" />
        <button
          onClick={handleSignOut}
          className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm text-fg-soft hover:bg-fg/5 hover:text-fg transition-colors"
        >
          <LogOut className="h-4 w-4 text-fg-muted" />
          Sign out
        </button>
      </div>
    </aside>
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
      className="w-full flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 text-sm text-fg-soft hover:bg-fg/5 hover:text-fg transition-colors"
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
