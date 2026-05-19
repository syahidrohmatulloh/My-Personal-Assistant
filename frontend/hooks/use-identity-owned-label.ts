"use client";

import { useEffect, useState } from "react";
import { getIdentity } from "@/lib/api";

type IdentityProfile = Record<string, unknown> | undefined | null;

function cleanString(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.trim();
  return cleaned.length > 0 ? cleaned : null;
}

function isGenericRoleName(value: string): boolean {
  return ["assistant", "ai assistant", "asisten", "ai", "bot"].includes(
    value.trim().toLowerCase(),
  );
}

function pickAssistantDisplayName(profile: IdentityProfile): string | null {
  const assistantName = cleanString(profile?.assistant_name);
  if (!assistantName) return null;
  if (isGenericRoleName(assistantName)) return null;
  return assistantName;
}

function pickUserDisplayName(profile: IdentityProfile): string | null {
  if (!profile) return null;

  const assistantName = pickAssistantDisplayName(profile);
  const assistantLowered = assistantName?.toLowerCase() ?? "";

  const candidates = [
    profile.name,
    profile.full_name,
    profile.preferred_name,
  ];

  for (const candidate of candidates) {
    const cleaned = cleanString(candidate);
    if (!cleaned) continue;

    const lowered = cleaned.toLowerCase();

    if (isGenericRoleName(cleaned)) continue;
    if (assistantLowered && lowered === assistantLowered) continue;

    return cleaned;
  }

  return null;
}

function useIdentityProfile(): IdentityProfile {
  const [profile, setProfile] = useState<IdentityProfile>(null);

  useEffect(() => {
    let mounted = true;

    getIdentity()
      .then((identity) => {
        if (!mounted) return;
        setProfile(identity?.profile ?? null);
      })
      .catch(() => {
        if (!mounted) return;
        setProfile(null);
      });

    return () => {
      mounted = false;
    };
  }, []);

  return profile;
}

export function useUserOwnedLabel(section: string): string {
  const profile = useIdentityProfile();
  const userDisplayName = pickUserDisplayName(profile);

  return userDisplayName ? `${userDisplayName} ${section}` : `Your ${section}`;
}

export function useAssistantOwnedLabel(section: string): string {
  const profile = useIdentityProfile();
  const assistantDisplayName = pickAssistantDisplayName(profile);

  return assistantDisplayName
    ? `${assistantDisplayName} ${section}`
    : `Assistant ${section}`;
}


export function useAssistantDisplayName(fallback = "Assistant"): string {
  const profile = useIdentityProfile();
  return pickAssistantDisplayName(profile) ?? fallback;
}
