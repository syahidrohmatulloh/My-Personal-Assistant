"use client";

import { memo } from "react";

type Props = {
  visible: boolean;
  assistantName?: string;
};

/**
 * Sticky "Assistant is typing" indicator (Phase 4.12).
 *
 * Sits at the top of the scroll viewport so it's visible during long
 * responses without scrolling back up. The wrapper always reserves its
 * height so toggling `visible` never causes layout jump — we only fade
 * opacity and lift translateY by a hair.
 *
 * Respects prefers-reduced-motion via globals.css (which kills transitions
 * globally when the user prefers reduced motion).
 *
 * Uses existing CSS tokens — no new colours, no new utility classes.
 */
function TypingIndicatorBase({ visible, assistantName = "Assistant" }: Props) {
  return (
    <div
      // Sticky at the top of the scroll container. z-10 keeps it above
      // bubble shadows but below modals/popovers (z-20+).
      className="sticky top-0 z-10 pointer-events-none flex justify-center"
      aria-live="polite"
      aria-atomic="true"
    >
      {/* Reserved-height inner so toggling visible doesn't shift content. */}
      <div className="h-7 flex items-center">
        <div
          className={[
            "inline-flex items-center gap-2 px-3 py-1 rounded-full",
            "text-[12px] italic text-fg-muted",
            "glass",
            "transition-opacity duration-200 ease-out",
            visible ? "opacity-100" : "opacity-0",
          ].join(" ")}
        >
          <span>{assistantName} is typing</span>
          <span className="flex items-center gap-0.5" aria-hidden="true">
            <span
              className="h-1 w-1 rounded-full bg-fg-muted pulse-dot"
              style={{ animationDelay: "0ms" }}
            />
            <span
              className="h-1 w-1 rounded-full bg-fg-muted pulse-dot"
              style={{ animationDelay: "180ms" }}
            />
            <span
              className="h-1 w-1 rounded-full bg-fg-muted pulse-dot"
              style={{ animationDelay: "360ms" }}
            />
          </span>
        </div>
      </div>
    </div>
  );
}

export const TypingIndicator = memo(TypingIndicatorBase);
