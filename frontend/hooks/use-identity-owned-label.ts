"use client";

import { useEffect, useState } from "react";
import { getIdentity } from "@/lib/api";

type IdentityProfile = Record<string, unknown> | undefined | null;

const USER_NAME_CACHE_KEY = "app:user-display-name";
const ASSISTANT_NAME_CACHE_KEY = "app:assistant-name";

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

function readCache(key: string): string | null {
  if (typeof window === "undefined") return null;

  try {
    const value = window.localStorage.getItem(key);
    return value && value.trim().length > 0 ? value.trim() : null;
  } catch {
    return null;
  }
}

function writeCache(key: string, value: string | null): void {
  if (typeof window === "undefined" || !value) return;

  try {
    window.localStorage.setItem(key, value);
  } catch {
    // Ignore storage failures.
  }
}

function useIdentityNames() {
  const [ready, setReady] = useState(false);
  const [profile, setProfile] = useState<IdentityProfile>(null);
  const [cachedUserName, setCachedUserName] = useState<string | null>(null);
  const [cachedAssistantName, setCachedAssistantName] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    const initialUserName = readCache(USER_NAME_CACHE_KEY);
    const initialAssistantName = readCache(ASSISTANT_NAME_CACHE_KEY);

    if (mounted) {
      setCachedUserName(initialUserName);
      setCachedAssistantName(initialAssistantName);
      setReady(true);
    }

    getIdentity()
      .then((identity) => {
        if (!mounted) return;

        const nextProfile = identity?.profile ?? null;
        const nextUserName = pickUserDisplayName(nextProfile);
        const nextAssistantName = pickAssistantDisplayName(nextProfile);

        setProfile(nextProfile);

        if (nextUserName) {
          setCachedUserName(nextUserName);
          writeCache(USER_NAME_CACHE_KEY, nextUserName);
        }

        if (nextAssistantName) {
          setCachedAssistantName(nextAssistantName);
          writeCache(ASSISTANT_NAME_CACHE_KEY, nextAssistantName);
        }

        setReady(true);
      })
      .catch(() => {
        if (!mounted) return;
        setProfile(null);
        setReady(true);
      });

    return () => {
      mounted = false;
    };
  }, []);

  const userDisplayName = pickUserDisplayName(profile) ?? cachedUserName;
  const assistantDisplayName = pickAssistantDisplayName(profile) ?? cachedAssistantName;

  return {
    ready,
    userDisplayName,
    assistantDisplayName,
  };
}

export function useUserOwnedLabel(section: string): string {
  const { ready, userDisplayName } = useIdentityNames();

  if (userDisplayName) return `${userDisplayName} ${section}`;
  if (!ready) return "\u00A0";

  return `Your ${section}`;
}

export function useAssistantOwnedLabel(section: string): string {
  const { ready, assistantDisplayName } = useIdentityNames();

  if (assistantDisplayName) return `${assistantDisplayName} ${section}`;
  if (!ready) return "\u00A0";

  return `Assistant ${section}`;
}

export function useAssistantDisplayName(fallback = "Assistant"): string {
  const { ready, assistantDisplayName } = useIdentityNames();

  if (assistantDisplayName) return assistantDisplayName;
  if (!ready) return "";

  return fallback;
}
