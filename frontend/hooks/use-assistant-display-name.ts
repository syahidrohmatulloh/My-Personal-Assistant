"use client";

import { useEffect, useState } from "react";

const ASSISTANT_NAME_COOKIE = "app-assistant-name";
const FALLBACK_ASSISTANT_NAME = "Assistant";

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;

  const prefix = `${name}=`;
  const item = document.cookie
    .split(";")
    .map((part) => part.trim())
    .find((part) => part.startsWith(prefix));

  if (!item) return null;

  try {
    return decodeURIComponent(item.slice(prefix.length)).trim() || null;
  } catch {
    return item.slice(prefix.length).trim() || null;
  }
}

export function getAssistantDisplayNameFromBrowser(): string {
  return readCookie(ASSISTANT_NAME_COOKIE) || FALLBACK_ASSISTANT_NAME;
}

export function useAssistantDisplayName(): string {
  const [assistantName, setAssistantName] = useState(FALLBACK_ASSISTANT_NAME);

  useEffect(() => {
    const sync = () => setAssistantName(getAssistantDisplayNameFromBrowser());

    sync();

    window.addEventListener("focus", sync);
    document.addEventListener("visibilitychange", sync);

    return () => {
      window.removeEventListener("focus", sync);
      document.removeEventListener("visibilitychange", sync);
    };
  }, []);

  return assistantName;
}
