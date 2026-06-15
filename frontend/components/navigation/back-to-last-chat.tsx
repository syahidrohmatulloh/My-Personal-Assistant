"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { useRouter } from "next/navigation";

const LAST_CHAT_PATH_KEY = "app:last-chat-path";

function getSafeLastChatPath(): string {
  const fallback = "/chat-v2";

  try {
    const stored = window.localStorage.getItem(LAST_CHAT_PATH_KEY);
    if (!stored) return fallback;

    const url = new URL(stored, window.location.origin);

    // Prevent cross-origin navigation.
    if (url.origin !== window.location.origin) return fallback;

    const pathname = url.pathname;

    // Only allow chat routes. This prevents loops back to settings/goals/etc.
    const isSafe =
      pathname === "/chat-v2" ||
      /^\/chat\/[A-Za-z0-9._~%:-]+\/?$/.test(pathname);

    if (!isSafe) return fallback;

    // Avoid pushing to the same page if somehow called from chat.
    if (pathname === window.location.pathname) return fallback;

    return `${pathname}${url.search}`;
  } catch {
    return fallback;
  }
}

type BackToLastChatProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  children?: ReactNode;
};

export function BackToLastChat({
  children = "Back to chat",
  type,
  onClick,
  ...props
}: BackToLastChatProps) {
  const router = useRouter();

  return (
    <button
      {...props}
      type={type ?? "button"}
      onClick={(event) => {
        onClick?.(event);
        if (event.defaultPrevented) return;
        router.push(getSafeLastChatPath());
      }}
    >
      {children}
    </button>
  );
}
