"use client";

import { ArrowLeft } from "lucide-react";
import { useRouter } from "next/navigation";

const LAST_CHAT_PATH_KEY = "assistant.lastChatPath";

export function BackToChatButton() {
  const router = useRouter();

  function handleBack() {
    const lastChatPath =
      typeof window !== "undefined"
        ? window.localStorage.getItem(LAST_CHAT_PATH_KEY)
        : null;

    if (lastChatPath && lastChatPath.startsWith("/chat")) {
      router.push(lastChatPath);
      return;
    }

    router.push("/chat");
  }

  return (
    <button
      type="button"
      onClick={handleBack}
      className="inline-flex items-center gap-2 text-sm text-fg-muted hover:text-fg transition-colors"
    >
      <ArrowLeft className="h-4 w-4" />
      Back to chat
    </button>
  );
}
