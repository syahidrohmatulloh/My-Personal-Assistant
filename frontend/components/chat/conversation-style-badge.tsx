"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Conversation,
  type StyleProfile,
  listConversations,
  listStyleProfiles,
  setConversationStyle,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Subtle indicator + picker for the active conversation style.
 *
 * Rules:
 * - If conversation has no style attached AND user has no profiles → render nothing.
 * - If conversation has no style attached BUT user has profiles → render small
 *   "Default" pill that lets user attach one without leaving the chat.
 * - If conversation has style → render the style name as a pill, clickable.
 *
 * Picker reuses the same logic as the sidebar's Change-style popover but
 * is anchored top-right of the chat area so it doesn't fight with the input.
 */
export function ConversationStyleBadge({ conversationId }: { conversationId: string }) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const { data: conversations = [] } = useQuery({
    queryKey: ["conversations"],
    queryFn: listConversations,
  });
  const { data: profiles = [] } = useQuery({
    queryKey: ["style-profiles"],
    queryFn: listStyleProfiles,
    staleTime: 60_000,
  });

  const convo = conversations.find((c) => c.id === conversationId);
  const currentId = convo?.style_profile_id ?? null;
  const currentProfile = currentId ? profiles.find((p) => p.id === currentId) : null;

  const styleMut = useMutation({
    mutationFn: (profileId: string | null) =>
      setConversationStyle(conversationId, profileId),
    onMutate: async (profileId) => {
      await qc.cancelQueries({ queryKey: ["conversations"] });
      const prev = qc.getQueryData<Conversation[]>(["conversations"]);
      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.map((c) =>
          c.id === conversationId ? { ...c, style_profile_id: profileId } : c,
        ),
      );
      return { prev };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prev) qc.setQueryData(["conversations"], ctx.prev);
    },
  });

  useEffect(() => {
    if (!open) return;
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    function onEsc(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onDocClick);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onDocClick);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  // Render nothing if user has no profiles AND no style is currently active.
  // Keeps default users' UI 100% unchanged.
  if (profiles.length === 0 && !currentProfile) return null;

  return (
    <div
      ref={ref}
      className="absolute right-3 sm:right-6 top-3 sm:top-4 z-10 pt-safe md:pt-0"
    >
      <button
        onClick={() => setOpen((v) => !v)}
        className={cn(
          "glass rounded-full px-2.5 py-1 text-[11px] inline-flex items-center gap-1.5 transition-colors",
          currentProfile
            ? "text-fg hover:bg-fg/5"
            : "text-fg-muted hover:text-fg hover:bg-fg/5",
        )}
        title="Change conversation style"
      >
        <Sparkles className="h-3 w-3" />
        <span className="truncate max-w-[140px]">
          {currentProfile ? currentProfile.profile_name : "Default"}
        </span>
      </button>
      {open && (
        <div
          className="absolute right-0 top-9 min-w-[200px] glass-strong rounded-lg shadow-lg shadow-black/20 border border-border py-1 overflow-hidden fade-up"
          role="menu"
        >
          <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-fg-subtle">
            Conversation style
          </p>
          <PickerOption
            label="Default"
            active={currentId === null}
            onClick={() => {
              styleMut.mutate(null);
              setOpen(false);
            }}
          />
          {profiles.map((p: StyleProfile) => (
            <PickerOption
              key={p.id}
              label={p.profile_name}
              active={currentId === p.id}
              onClick={() => {
                styleMut.mutate(p.id);
                setOpen(false);
              }}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function PickerOption({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "w-full flex items-center justify-between gap-2 px-3 py-1.5 text-xs text-left transition-colors truncate",
        active ? "bg-accent-soft text-fg font-medium" : "text-fg-soft hover:bg-fg/5 hover:text-fg",
      )}
    >
      <span className="truncate">{label}</span>
      {active && <span className="text-[10px] text-accent shrink-0">●</span>}
    </button>
  );
}
