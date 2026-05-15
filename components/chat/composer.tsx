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
    el.style.height = Math.min(el.scrollHeight, 200) + "px";
  }, [value]);

  function handleKey(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!disabled && value.trim()) onSubmit();
    }
  }

  return (
    <div className="px-4 pb-4 sm:px-6">
      <div className="max-w-3xl mx-auto">
        <div className="glass-strong rounded-2xl p-2 flex items-end gap-2 focus-within:ring-2 focus-within:ring-accent/30 transition-all">
          <textarea
            ref={ref}
            rows={1}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Message your assistant…"
            className="flex-1 resize-none bg-transparent px-3 py-2 text-[15px] text-fg placeholder:text-fg-subtle focus:outline-none max-h-[200px]"
          />
          <button
            onClick={onSubmit}
            disabled={disabled || !value.trim()}
            className="h-9 w-9 shrink-0 grid place-items-center rounded-xl bg-accent text-on-accent hover:bg-accent-hover disabled:opacity-30 disabled:cursor-not-allowed transition-all active:scale-95 shadow-md shadow-accent/25"
            aria-label="Send"
          >
            <ArrowUp className="h-4 w-4" strokeWidth={2.5} />
          </button>
        </div>
        <p className="text-[11px] text-fg-subtle mt-2 text-center">
          Shift + Enter for newline · Enter to send
        </p>
      </div>
    </div>
  );
}
