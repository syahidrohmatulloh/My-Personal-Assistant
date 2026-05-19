"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

const LAST_CHAT_PATH_KEY = "app:last-chat-path";

function isSafeChatPath(pathname: string): boolean {
  if (!pathname) return false;

  // Only store actual chat routes.
  // This intentionally excludes /goals, /settings, /identity, /journal, etc.
  if (pathname === "/chat") return true;
  if (/^\/chat\/[A-Za-z0-9._~%:-]+\/?$/.test(pathname)) return true;

  return false;
}

export function LastChatTracker() {
  const pathname = usePathname();

  useEffect(() => {
    if (!pathname || !isSafeChatPath(pathname)) return;

    const fullPath = `${pathname}${window.location.search || ""}`;

    try {
      window.localStorage.setItem(LAST_CHAT_PATH_KEY, fullPath);
    } catch {
      // Ignore private mode / storage errors.
    }
  }, [pathname]);

  return null;
}
