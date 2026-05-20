"use client";

import { cn } from "@/lib/utils";
import type { AvatarProfile } from "@/lib/avatar-mode-api";

export type AssistantAvatarState = "idle" | "typing" | "speaking" | "disabled";

type AssistantAvatarProps = {
  profile?: AvatarProfile | null;
  assistantName: string;
  state?: AssistantAvatarState;
  size?: "sm" | "md" | "lg";
  className?: string;
};

const sizeClass = {
  sm: "h-8 w-8 text-[10px]",
  md: "h-10 w-10 text-xs",
  lg: "h-14 w-14 text-sm",
};

function initialsFromName(name: string): string {
  const parts = name
    .trim()
    .split(/\s+/)
    .filter(Boolean);

  if (parts.length === 0) return "AI";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return `${parts[0][0] ?? ""}${parts[1][0] ?? ""}`.toUpperCase() || "AI";
}

export function AssistantAvatar({
  profile,
  assistantName,
  state = "idle",
  size = "sm",
  className,
}: AssistantAvatarProps) {
  const label = assistantName.trim() || "Assistant";
  const enabled =
    state !== "disabled" &&
    profile?.avatar_mode_enabled === true &&
    profile?.consent_confirmed === true &&
    Boolean(profile?.image_url);

  if (!enabled) {
    return (
      <div
        aria-label={label}
        title={label}
        className={cn(
          "shrink-0 rounded-full border border-border bg-fg/5 font-medium text-fg-muted flex items-center justify-center",
          sizeClass[size],
          className,
        )}
      >
        {initialsFromName(label)}
      </div>
    );
  }

  const isActive = state === "typing" || state === "speaking";

  return (
    <div className={cn("relative shrink-0", sizeClass[size], className)} aria-label={label} title={label}>
      <span
        aria-hidden="true"
        className={cn(
          "absolute inset-0 rounded-full border border-accent/25",
          isActive ? "animate-ping opacity-40" : "opacity-0",
        )}
      />
      <span
        aria-hidden="true"
        className={cn(
          "absolute inset-0 rounded-full bg-accent/10 blur-sm transition-opacity duration-500",
          isActive ? "opacity-100" : "opacity-30",
        )}
      />
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={profile!.image_url!}
        alt={label}
        className={cn(
          "relative h-full w-full rounded-full object-cover border border-white/10 shadow-sm transition-transform duration-700",
          state === "idle" && profile?.animation_style !== "minimal" ? "animate-pulse" : "",
          state === "typing" ? "scale-[1.03]" : "scale-100",
        )}
        loading="lazy"
        referrerPolicy="no-referrer"
      />
      {isActive ? (
        <span
          aria-hidden="true"
          className="absolute bottom-1 left-1/2 h-1 w-3 -translate-x-1/2 rounded-full bg-white/70 animate-pulse"
        />
      ) : null}
    </div>
  );
}
