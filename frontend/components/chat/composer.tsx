"use client";

import { useEffect, useRef, useState } from "react";
import {ArrowUp, FileText, ImageIcon, Loader2, Paperclip, X, Mic, Square} from "lucide-react";
import { type AttachmentMeta, uploadAttachment } from "@/lib/api";
import { useVoiceInput } from "@/hooks/use-voice-input";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: (attachmentIds: string[]) => void;
  disabled?: boolean;
};

type PendingUpload =
  | { kind: "uploading"; clientId: string; filename: string; fileKind: "image" | "document" }
  | { kind: "done"; clientId: string; meta: AttachmentMeta }
  | { kind: "error"; clientId: string; filename: string; error: string };

const ACCEPT = "image/jpeg,image/png,image/gif,image/webp,application/pdf";

export function Composer({ value, onChange, onSubmit, disabled }: Props) {
  const voiceInput = useVoiceInput({ language: "multi" });
  const voiceBusy = voiceInput.isRecording || voiceInput.isTranscribing;

  async function handleVoiceClick() {
    if (disabled || voiceInput.isTranscribing) return;

    if (!voiceInput.isRecording) {
      await voiceInput.start();
      return;
    }

    const transcript = await voiceInput.stopAndTranscribe();
    if (!transcript) return;

    const nextValue = value.trim() ? `${value.trim()} ${transcript}` : transcript;
    onChange(nextValue);
  }
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);
  const [pending, setPending] = useState<PendingUpload[]>([]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  function fileKind(mt: string): "image" | "document" {
    return mt.startsWith("image/") ? "image" : "document";
  }

  async function handleFiles(files: FileList | null) {
    if (!files || !files.length) return;
    for (const file of Array.from(files).slice(0, 10)) {
      const clientId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
      const kind = fileKind(file.type);
      setPending((p) => [
        ...p,
        { kind: "uploading", clientId, filename: file.name, fileKind: kind },
      ]);
      try {
        const meta = await uploadAttachment(file);
        setPending((p) =>
          p.map((x) =>
            x.clientId === clientId ? { kind: "done", clientId, meta } : x,
          ),
        );
      } catch (err) {
        setPending((p) =>
          p.map((x) =>
            x.clientId === clientId
              ? {
                  kind: "error",
                  clientId,
                  filename: file.name,
                  error: err instanceof Error ? err.message : "Upload failed",
                }
              : x,
          ),
        );
      }
    }
  }

  function removePending(clientId: string) {
    setPending((p) => p.filter((x) => x.clientId !== clientId));
  }

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      const isMobile = window.matchMedia("(max-width: 640px)").matches;
      if (!isMobile) {
        e.preventDefault();
        trySubmit();
      }
    }
  }

  function trySubmit() {
    const hasContent = value.trim().length > 0 || pending.some((p) => p.kind === "done");
    if (!hasContent || disabled) return;
    if (pending.some((p) => p.kind === "uploading")) return; // wait for uploads
    const attachmentIds = pending
      .filter((p): p is Extract<PendingUpload, { kind: "done" }> => p.kind === "done")
      .map((p) => p.meta.id);
    onSubmit(attachmentIds);
    setPending([]);
  }

  const uploadingCount = pending.filter((p) => p.kind === "uploading").length;
  const canSend =
    (value.trim().length > 0 || pending.some((p) => p.kind === "done")) &&
    uploadingCount === 0 &&
    !disabled;

  return (
    <div className="sticky bottom-0 px-3 sm:px-6 pb-2 sm:pb-4 pb-safe">
      {/* Pi.ai-feel composer (Phase 4.12 polish):
          - max-w-3xl matches the message column above for visual continuity
          - rounded-3xl + glass + soft floating shadow gives the floating
            composer effect without leaving the calm aesthetic
          - focus-within ring is gentler than before (ring-1 on the accent
            with a lower alpha) and the shadow lifts a hair
          - desktop text-[17px] / mobile text-base (16px) — mobile must stay
            at 16px to avoid iOS auto-zoom; globals.css enforces this. */}
      <div className="max-w-3xl mx-auto">
        {/* Attachment chips above the input */}
        {pending.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-2 px-1">
            {pending.map((p) => (
              <AttachmentChip
                key={p.clientId}
                item={p}
                onRemove={() => removePending(p.clientId)}
              />
            ))}
          </div>
        )}

        <div
          className={[
            "glass-strong rounded-3xl p-1.5 sm:p-2 flex items-end gap-1.5 sm:gap-2",
            // Soft floating shadow — uses existing accent token so theme stays consistent.
            // Subtle in idle state; gains a touch of glow on focus-within.
            "shadow-[0_8px_24px_-12px_rgb(0_0_0_/_0.18)]",
            "focus-within:shadow-[0_12px_32px_-12px_rgb(0_0_0_/_0.22)]",
            "focus-within:ring-1 focus-within:ring-accent/25",
            "transition-shadow duration-200 ease-out",
          ].join(" ")}
        >
          <button
            type="button"
            onClick={() => fileRef.current?.click()}
            disabled={disabled}
            className="h-10 w-10 sm:h-9 sm:w-9 shrink-0 grid place-items-center rounded-2xl text-fg-muted hover:text-fg hover:bg-fg/5 active:bg-fg/10 disabled:opacity-30 transition-colors"
            aria-label="Attach file"
          >
            <Paperclip className="h-4 w-4" />
          </button>
          <input
            ref={fileRef}
            type="file"
            accept={ACCEPT}
            multiple
            className="hidden"
            onChange={(e) => {
              handleFiles(e.target.files);
              e.target.value = ""; // allow re-uploading same file
            }}
          />
          <button
            type="button"
            onClick={handleVoiceClick}
            disabled={disabled || voiceInput.isTranscribing}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-border bg-fg/[0.035] text-fg-muted transition hover:bg-fg/[0.06] hover:text-fg disabled:cursor-not-allowed disabled:opacity-50"
            aria-label={
              voiceInput.isRecording
                ? "Stop recording and transcribe"
                : voiceInput.isTranscribing
                  ? "Transcribing voice"
                  : "Record voice"
            }
            title={
              voiceInput.isRecording
                ? "Stop recording and transcribe"
                : voiceInput.isTranscribing
                  ? "Transcribing voice"
                  : "Record voice"
            }
          >
            {voiceInput.isTranscribing ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : voiceInput.isRecording ? (
              <Square className="h-3.5 w-3.5 fill-current" />
            ) : (
              <Mic className="h-4 w-4" />
            )}
          </button>
          <textarea
            ref={textareaRef}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Message your assistant…"
            enterKeyHint="send"
            autoCapitalize="sentences"
            autoCorrect="on"
            spellCheck
            // text-base on mobile (16px — avoids iOS auto-zoom; globals.css
            // forces 16px on <640px regardless).
            // sm:text-[17px] on desktop — premium, readable, calm.
            className="flex-1 resize-none bg-transparent px-2.5 py-2.5 text-base sm:text-[17px] text-fg placeholder:text-fg-subtle focus:outline-none max-h-[160px] leading-[1.6]"
          />
          <button
            onClick={trySubmit}
            disabled={!canSend}
            className="h-10 w-10 sm:h-9 sm:w-9 shrink-0 grid place-items-center rounded-2xl bg-accent text-on-accent hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-95 shadow-md shadow-accent/25"
            aria-label="Send"
          >
            <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
          </button>
        </div>
        {uploadingCount > 0 && (
          <p className="text-[11px] text-fg-subtle mt-2 text-center">
            Uploading {uploadingCount} file{uploadingCount > 1 ? "s" : ""}…
          </p>
        )}
        <p className="hidden sm:block text-[11px] text-fg-subtle mt-2 text-center">
          {voiceInput.error ? <span className="text-[11px] text-red-500">{voiceInput.error}</span> : null}
          Shift + Enter for newline · Enter to send
        </p>
      </div>
    </div>
  );
}

function AttachmentChip({
  item,
  onRemove,
}: {
  item: PendingUpload;
  onRemove: () => void;
}) {
  const isImage =
    (item.kind === "uploading" || item.kind === "error")
      ? (item as Extract<PendingUpload, { fileKind: "image" | "document" } | { filename: string }>).kind === "uploading"
        ? (item as Extract<PendingUpload, { kind: "uploading" }>).fileKind === "image"
        : false
      : item.meta.kind === "image";

  const label =
    item.kind === "done"
      ? item.meta.original_filename
      : item.kind === "uploading"
        ? item.filename
        : item.filename;

  return (
    <div
      className={`group glass rounded-lg px-2 py-1 text-xs flex items-center gap-1.5 max-w-[200px] ${
        item.kind === "error" ? "border border-danger/40" : ""
      }`}
    >
      {item.kind === "uploading" ? (
        <Loader2 className="h-3 w-3 animate-spin text-fg-muted shrink-0" />
      ) : isImage ? (
        <ImageIcon className="h-3 w-3 text-fg-muted shrink-0" />
      ) : (
        <FileText className="h-3 w-3 text-fg-muted shrink-0" />
      )}
      <span className="truncate text-fg-soft">
        {item.kind === "error" ? item.error : label}
      </span>
      <button
        onClick={onRemove}
        className="text-fg-subtle hover:text-fg shrink-0"
        aria-label="Remove attachment"
      >
        <X className="h-3 w-3" />
      </button>
    </div>
  );
}
