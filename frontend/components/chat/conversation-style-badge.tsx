"use client";

import { useEffect, useRef, useState } from "react";
import { Sparkles } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type Conversation,
  type StyleProfile,
  listStyleProfiles,
  setConversationStyle,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Subtle indicator + picker for the active conversation style.
 *
 * Rules:
 * - If conversation has no style attached → render nothing.
 * - If conversation has style → render the style name as a pill, clickable.
 *
 * Default should feel invisible, not like a mode the user needs to manage.
 */
export function ConversationStyleBadge({
  conversationId,
  initialStyleProfileId = null,
  initialStyleProfileName = null,
}: {
  conversationId: string
  initialStyleProfileId?: string | null
  initialStyleProfileName?: string | null
}) {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const [currentId, setCurrentId] = useState<string | null>(initialStyleProfileId);
  const [currentName, setCurrentName] = useState<string | null>(initialStyleProfileName);

  const { data: profiles = [] } = useQuery({
    queryKey: ["style-profiles"],
    queryFn: listStyleProfiles,
    enabled: open,
    staleTime: 60_000,
  });

  const currentProfile =
    currentId
      ? profiles.find((p) => p.id === currentId) ??
        (currentName
          ? {
              id: currentId,
              profile_name: currentName,
            }
          : null)
      : null;

  const styleMut = useMutation({
    mutationFn: (profileId: string | null) =>
      setConversationStyle(conversationId, profileId),
    onMutate: async (profileId) => {
      await qc.cancelQueries({ queryKey: ["conversations"] });

      const prevConversations = qc.getQueryData<Conversation[]>(["conversations"]);
      const previousId = currentId;
      const previousName = currentName;
      const nextName =
        profileId == null
          ? null
          : profiles.find((profile) => profile.id === profileId)?.profile_name ?? null;

      setCurrentId(profileId);
      setCurrentName(nextName);

      qc.setQueryData<Conversation[]>(["conversations"], (old = []) =>
        old.map((conversation) =>
          conversation.id === conversationId
            ? { ...conversation, style_profile_id: profileId }
            : conversation,
        ),
      );

      return { prevConversations, previousId, previousName };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.prevConversations) {
        qc.setQueryData(["conversations"], ctx.prevConversations);
      }

      setCurrentId(ctx?.previousId ?? null);
      setCurrentName(ctx?.previousName ?? null);
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

  // Default style should be invisible. Only show the badge when a style
  // profile is actively attached to this conversation.
  if (!currentProfile) return null;

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
          {currentProfile.profile_name}
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
                setCurrentName(p.profile_name);
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
