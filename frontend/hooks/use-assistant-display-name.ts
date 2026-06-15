"use client";

import { useEffect, useState } from "react";
import { getIdentity } from "@/lib/api";

const FALLBACK_ASSISTANT_NAME = "Aliyya";
const ASSISTANT_NAME_CACHE_KEY = "app:assistant-name";

function cleanAssistantName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.trim();
  return cleaned.length > 0 ? cleaned : null;
}

export function getAssistantDisplayNameFromBrowser(): string {
  if (typeof window === "undefined") return FALLBACK_ASSISTANT_NAME;

  try {
    const value = window.localStorage.getItem(ASSISTANT_NAME_CACHE_KEY);
    return cleanAssistantName(value) || FALLBACK_ASSISTANT_NAME;
  } catch {
    return FALLBACK_ASSISTANT_NAME;
  }
}

export function useAssistantDisplayName(fallback = FALLBACK_ASSISTANT_NAME): string {
  const [assistantName, setAssistantName] = useState<string>("");

  useEffect(() => {
    let mounted = true;

    getIdentity()
      .then((identity) => {
        if (!mounted) return;

        const nextName = cleanAssistantName(identity?.profile?.assistant_name);

        if (nextName) {
          setAssistantName(nextName);

          try {
            window.localStorage.setItem(ASSISTANT_NAME_CACHE_KEY, nextName);
          } catch {}

          return;
        }

        setAssistantName(fallback);
      })
      .catch(() => {
        if (!mounted) return;
        setAssistantName(fallback);
      });

    return () => {
      mounted = false;
    };
  }, [fallback]);

  return assistantName;
}
