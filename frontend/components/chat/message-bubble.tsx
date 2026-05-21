"use client";

import { memo, useState } from "react";
import { AssistantAvatar } from "@/components/avatar/AssistantAvatar";
import { useAssistantDisplayName } from "@/hooks/use-assistant-display-name";
import { useAvatarProfile } from "@/hooks/use-avatar-mode";
import { useAvatarActivity } from "@/hooks/use-avatar-activity";
import { useAvatarAudioPlayer } from "@/hooks/use-avatar-audio-player";
import { Loader2, Volume2, VolumeX } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import { speakText } from "@/lib/voice-api";
import { cn } from "@/lib/utils";

type Props = {
  role: "user" | "assistant";
  content: string;
  pending?: boolean;
};

function MessageBubbleBase({ role, content, pending }: Props) {
  const isUser = role === "user";
  const assistantName = useAssistantDisplayName();
  const { data: avatarProfile } = useAvatarProfile();
  const avatarActivity = useAvatarActivity();
  const avatarAudio = useAvatarAudioPlayer();
  const [speakError, setSpeakError] = useState<string | null>(null);


  async function handleSpeak() {
    if (isUser || avatarAudio.isPlaying) return;

    const textToSpeak = content.trim();
    if (!textToSpeak) return;

    setSpeakError(null);

    try {
      const response = await speakText(textToSpeak);
      await avatarAudio.playResponse(response, "voice");
    } catch (error) {
      setSpeakError(error instanceof Error ? error.message : "Speech playback failed.");
    }
  }

  return (
    <div className={cn("flex w-full fade-up items-start gap-2", isUser ? "justify-end" : "justify-start")}>
      {!isUser ? (
        <AssistantAvatar
          profile={avatarProfile}
          assistantName={assistantName}
          state={avatarActivity === "speaking" ? "speaking" : pending ? "typing" : "idle"}
          size="sm"
          className="mt-1"
        />
      ) : null}
      <div
        className={cn(
          // Bubbles take more width on mobile (less wasted space), tighter on desktop.
          // Padding tightens on mobile too.
          "max-w-[92%] sm:max-w-[78%] rounded-2xl px-3.5 py-2.5 sm:px-4 sm:py-3",
          "text-[15px] leading-relaxed",
          isUser
            ? "bg-accent text-on-accent shadow-lg shadow-accent/20"
            : "glass text-fg",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{content}</p>
        ) : (
          <div className="prose-chat break-words">
            {content ? (
              <ReactMarkdown
                remarkPlugins={[remarkGfm]}
                rehypePlugins={[rehypeHighlight]}
              >
                {content}
              </ReactMarkdown>
            ) : pending ? (
              <PendingDots />
            ) : null}

            {content ? (
              <div className="not-prose mt-2 flex items-center gap-2">
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
    a.role === b.role && a.content === b.content && a.pending === b.pending,
);

function PendingDots() {
  return (
    <div className="flex items-center gap-1.5 py-1">
      <span className="h-2 w-2 rounded-full bg-accent pulse-dot" style={{ animationDelay: "0ms" }} />
      <span className="h-2 w-2 rounded-full bg-accent pulse-dot" style={{ animationDelay: "200ms" }} />
      <span className="h-2 w-2 rounded-full bg-accent pulse-dot" style={{ animationDelay: "400ms" }} />
    </div>
  );
}
