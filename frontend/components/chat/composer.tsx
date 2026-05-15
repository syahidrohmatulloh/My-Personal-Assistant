"use client";

import { useEffect, useRef } from "react";
import { ArrowUp } from "lucide-react";

type Props = {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  disabled?: boolean;
};

export function Composer({ value, onChange, onSubmit, disabled }: Props) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 160) + "px";
  }, [value]);

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    // On desktop: Enter sends, Shift+Enter newline.
    // On mobile: Enter always newlines (user taps Send button).
    if (e.key === "Enter" && !e.shiftKey) {
      const isMobile = window.matchMedia("(max-width: 640px)").matches;
      if (!isMobile) {
        e.preventDefault();
        if (!disabled && value.trim()) onSubmit();
      }
    }
  }

  return (
    // sticky-bottom + safe-area. On mobile, iOS will push this above the keyboard
    // automatically when the textarea is focused (because of dvh on the parent).
    <div className="sticky bottom-0 px-3 sm:px-6 pb-2 sm:pb-4 pb-safe">
      <div className="max-w-3xl mx-auto">
        <div className="glass-strong rounded-2xl p-1.5 sm:p-2 flex items-end gap-1.5 sm:gap-2 focus-within:ring-2 focus-within:ring-accent/30 transition-all">
          <textarea
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Message your assistant…"
            enterKeyHint="send"
            autoCapitalize="sentences"
            autoCorrect="on"
            spellCheck
            className="flex-1 resize-none bg-transparent px-3 py-2.5 text-base sm:text-[15px] text-fg placeholder:text-fg-subtle focus:outline-none max-h-[160px] leading-relaxed"
          />
          <button
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            className="h-10 w-10 sm:h-9 sm:w-9 shrink-0 grid place-items-center rounded-xl bg-accent text-on-accent hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-95 shadow-md shadow-accent/25"
            aria-label="Send"
          >
            <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
          </button>
        </div>
        {/* Hint only on desktop — mobile users don't need it and the line wastes vertical space. */}
        <p className="hidden sm:block text-[11px] text-fg-subtle mt-2 text-center">
          Shift + Enter for newline · Enter to send
        </p>
      </div>
    </div>
  );
}
