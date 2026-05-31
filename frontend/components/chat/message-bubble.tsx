"use client";

import { memo, useEffect, useRef, useState } from "react";
import { Loader2, Volume2, VolumeX } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";

import { AssistantAvatar } from "@/components/avatar/AssistantAvatar";
import { useAssistantDisplayName } from "@/hooks/use-assistant-display-name";
import { useAvatarActivity } from "@/hooks/use-avatar-activity";
import { useAvatarAudioPlayer } from "@/hooks/use-avatar-audio-player";
import { useAvatarProfile } from "@/hooks/use-avatar-mode";
import { speakText } from "@/lib/voice-api";
import { cn } from "@/lib/utils";

type Props = {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
  timestamp?: string;
};

function MessageBubbleBase({ role, content, pending, timestamp }: Props) {
  const isUser = role === "user";
  const assistantName = useAssistantDisplayName();
  const { data: avatarProfile } = useAvatarProfile();
  const avatarActivity = useAvatarActivity();
  const avatarAudio = useAvatarAudioPlayer();
  const [speakError, setSpeakError] = useState<string | null>(null);
  const [entered, setEntered] = useState(false);

  const displayContent = useStreamingText(content, !isUser && pending === true);

  useEffect(() => {
    const frameId = window.requestAnimationFrame(() => setEntered(true));
    return () => window.cancelAnimationFrame(frameId);
  }, []);

  async function handleSpeak() {
    if (isUser || avatarAudio.isPlaying) return;

    const textToSpeak = content.trim();
    if (!textToSpeak) return;

    setSpeakError(null);

    try {
      const response = await speakText(textToSpeak);
      await avatarAudio.playResponse(response, "voice");
    } catch (error) {
      const message =
        error instanceof Error && error.message
          ? error.message
          : "Audio belum bisa diputar. Coba tap Speak lagi.";
      setSpeakError(message);
    }
  }

  const isThinking = !isUser && pending && !content.trim();

  if (isThinking) {
    return (
      <div
        className={cn(
          "flex w-full items-start justify-start gap-3 transition-all duration-500 ease-out",
          entered ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
        )}
      >
        <AssistantAvatar
          profile={avatarProfile}
          assistantName={assistantName}
          state="typing"
          size="sm"
          className="mt-1.5"
        />

        <div className="px-2 py-3 text-fg">
          <PendingDots />
        </div>
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex w-full items-start gap-3 transition-all duration-500 ease-out",
        isUser ? "justify-end" : "justify-start",
        entered ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0",
      )}
    >
      {!isUser ? (
        <AssistantAvatar
          profile={avatarProfile}
          assistantName={assistantName}
          state={avatarActivity === "speaking" ? "speaking" : pending ? "typing" : "idle"}
          size="sm"
          className="mt-1.5"
        />
      ) : null}

      <div
        className={cn(
          "max-w-[92%] sm:max-w-[78%] rounded-[1.35rem] px-4 py-3 sm:px-5 sm:py-4",
          "text-[16.5px] leading-[1.72] sm:text-[17px] sm:leading-[1.78]",
          isUser
            ? "bg-accent text-on-accent shadow-lg shadow-accent/20"
            : "glass text-fg shadow-sm",
        )}
      >
        {isUser ? (
          <div>
            <p className="whitespace-pre-wrap break-words">{content}</p>
            {timestamp ? (
              <div className="mt-1 text-right text-[10px] leading-none text-on-accent/70">
                {timestamp}
              </div>
            ) : null}
          </div>
        ) : (
          <div className="prose-chat break-words">
            {displayContent ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {displayContent}
              </ReactMarkdown>
            ) : null}

            {content && !pending ? (
              <div className="not-prose mt-3 flex items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2">
                  <button
                    type="button"
                    onClick={handleSpeak}
                    disabled={avatarAudio.isPlaying}
                    className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-fg/[0.03] px-2.5 text-[11px] font-medium text-fg-muted transition hover:bg-fg/[0.06] hover:text-fg disabled:cursor-not-allowed disabled:opacity-60"
                    aria-label={avatarAudio.isPlaying ? "Playing voice" : "Speak message"}
                    title={avatarAudio.isPlaying ? "Playing voice" : "Speak message"}
                  >
                    {avatarAudio.isPlaying ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    ) : (
                      <Volume2 className="h-3.5 w-3.5" />
                    )}
                    {avatarAudio.isPlaying ? "Playing" : "Speak"}
                  </button>

                  {avatarAudio.isPlaying ? (
                    <button
                      type="button"
                      onClick={avatarAudio.stop}
                      className="inline-flex h-7 items-center gap-1.5 rounded-full border border-border bg-fg/[0.03] px-2.5 text-[11px] font-medium text-fg-muted transition hover:bg-fg/[0.06] hover:text-fg"
                      aria-label="Stop voice"
                      title="Stop voice"
                    >
                      <VolumeX className="h-3.5 w-3.5" />
                      Stop
                    </button>
                  ) : null}
                </div>

                {timestamp ? (
                  <span className="shrink-0 self-end pb-0.5 text-[10px] leading-none text-fg-subtle">
                    {timestamp}
                  </span>
                ) : null}
              </div>
            ) : timestamp ? (
              <div className="not-prose mt-2 text-right text-[10px] leading-none text-fg-subtle">
                {timestamp}
              </div>
            ) : null}

            {speakError ? <p className="not-prose mt-2 text-[11px] text-red-500">{speakError}</p> : null}
          </div>
        )}
      </div>
    </div>
  );
}

export const MessageBubble = memo(
  MessageBubbleBase,
  (a, b) =>
    a.role === b.role &&
    a.content === b.content &&
    a.pending === b.pending &&
    a.timestamp === b.timestamp,
);

function useStreamingText(content: string, active: boolean) {
  const prefersReducedMotion = usePrefersReducedMotion();
  const [displayed, setDisplayed] = useState(() => (active && !prefersReducedMotion ? "" : content));

  const targetRef = useRef(active && !prefersReducedMotion ? "" : content);
  const displayedRef = useRef(displayed);
  const activeRef = useRef(active);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    displayedRef.current = displayed;
  }, [displayed]);

  useEffect(() => {
    activeRef.current = active;
  }, [active]);

  useEffect(() => {
    if (prefersReducedMotion) {
      targetRef.current = content;
      displayedRef.current = content;
      setDisplayed(content);
      return;
    }

    const previousTarget = targetRef.current;

    if (!content.startsWith(previousTarget) && content !== previousTarget) {
      targetRef.current = content;
      displayedRef.current = active ? "" : content;
      setDisplayed(displayedRef.current);
    } else {
      targetRef.current = content;
    }

    if (timerRef.current == null) {
      timerRef.current = window.setInterval(() => {
        const target = targetRef.current;
        const current = displayedRef.current;

        if (current.length >= target.length) {
          if (!activeRef.current && timerRef.current != null) {
            window.clearInterval(timerRef.current);
            timerRef.current = null;
          }
          return;
        }

        const remaining = target.length - current.length;
        const step = remaining > 500 ? 14 : remaining > 180 ? 9 : remaining > 60 ? 6 : 3;
        const next = target.slice(0, current.length + step);

        displayedRef.current = next;
        setDisplayed(next);
      }, 34);
    }
  }, [active, content, prefersReducedMotion]);

  useEffect(() => {
    return () => {
      if (timerRef.current != null) {
        window.clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, []);

  return displayed;
}

function PendingDots() {
  return (
    <div className="not-prose flex items-center gap-2.5 text-fg" aria-label="Assistant is thinking">
      <span
        className="h-2.5 w-2.5 rounded-full bg-current"
        style={{ animation: "mpa-dot-bounce 0.9s infinite ease-in-out", animationDelay: "0ms" }}
      />
      <span
        className="h-2.5 w-2.5 rounded-full bg-current opacity-80"
        style={{ animation: "mpa-dot-bounce 0.9s infinite ease-in-out", animationDelay: "140ms" }}
      />
      <span
        className="h-2.5 w-2.5 rounded-full bg-current opacity-60"
        style={{ animation: "mpa-dot-bounce 0.9s infinite ease-in-out", animationDelay: "280ms" }}
      />
      <style jsx>{`
        @keyframes mpa-dot-bounce {
          0%, 80%, 100% {
            transform: translateY(0);
            opacity: 0.45;
          }
          40% {
            transform: translateY(-7px);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  );
}

function usePrefersReducedMotion() {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false);

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

    const sync = () => setPrefersReducedMotion(mediaQuery.matches);
    sync();

    mediaQuery.addEventListener("change", sync);

    return () => {
      mediaQuery.removeEventListener("change", sync);
    };
  }, []);

  return prefersReducedMotion;
}
