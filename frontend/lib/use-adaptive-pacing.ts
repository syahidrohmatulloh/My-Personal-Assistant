"use client";

import { useCallback, useEffect, useRef } from "react";
import type { Pacing } from "@/lib/api";

/**
 * Adaptive token pacing layer (Phase 4.12).
 *
 * Why:
 *   When the backend streams tokens faster than feels human, the assistant
 *   reads like a printer. This hook queues incoming text and drains it on
 *   a per-character cadence based on a pacing hint from the backend
 *   (or a frontend heuristic if the hint is absent). The user perceives
 *   a calm, human-paced reveal.
 *
 * What it is NOT:
 *   - NOT a buffer that holds back the whole response. Worst case it
 *     adds up to ~2s of buffering and then fast-forwards.
 *   - NOT a polling timer. Uses a single requestAnimationFrame loop,
 *     ~60Hz on most displays, paused when the queue is empty.
 *   - NOT applied when prefers-reduced-motion is on. The hook flushes
 *     instantly in that case — accessibility first.
 *
 * Backlog guard:
 *   If the queue grows past MAX_QUEUE_CHARS we drop into "immediate"
 *   mode for the rest of the message — long responses don't feel
 *   frustrating.
 *
 * Code block guard:
 *   Once the assistant emits a triple-backtick fence we flip to
 *   "immediate" until end of message. Code shouldn't be revealed
 *   character-by-character; it should land.
 */

// Tunables — keep these together so they're easy to find later.
const MS_PER_CHAR: Record<Pacing, number> = {
  immediate: 0,
  fast: 4,
  natural: 11,
  slow: 18,
};
const MAX_QUEUE_CHARS = 800; // beyond this we fast-forward
const CHARS_PER_FRAME_CAP = 32; // never reveal more than this in one rAF tick

type Options = {
  onText: (text: string) => void;
};

type Handle = {
  push: (text: string) => void;
  setPacing: (p: Pacing) => void;
  flush: () => void;
  reset: () => void;
};

export function useAdaptivePacing({ onText }: Options): Handle {
  // Refs only — this hook never re-renders.
  const queueRef = useRef<string>("");
  const pacingRef = useRef<Pacing>("natural");
  const lastTickRef = useRef<number>(0);
  const rafRef = useRef<number | null>(null);
  const reducedMotionRef = useRef<boolean>(false);
  const codeFenceRef = useRef<boolean>(false);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;

  // Detect reduced-motion preference once, plus listen for changes.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    reducedMotionRef.current = mq.matches;
    const handler = (e: MediaQueryListEvent) => {
      reducedMotionRef.current = e.matches;
    };
    // Safari < 14 uses addListener; modern uses addEventListener
    if (mq.addEventListener) mq.addEventListener("change", handler);
    else mq.addListener(handler);
    return () => {
      if (mq.removeEventListener) mq.removeEventListener("change", handler);
      else mq.removeListener(handler);
    };
  }, []);

  // Cleanup any in-flight rAF on unmount.
  useEffect(() => {
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  const tick = useCallback((now: number) => {
    rafRef.current = null;
    const queue = queueRef.current;
    if (!queue) {
      lastTickRef.current = 0;
      return;
    }

    // Decide effective pacing for this tick.
    let pacing = pacingRef.current;
    if (reducedMotionRef.current) pacing = "immediate";
    else if (codeFenceRef.current) pacing = "immediate";
    else if (queue.length > MAX_QUEUE_CHARS) pacing = "immediate";

    if (pacing === "immediate") {
      // Drain everything in one shot.
      queueRef.current = "";
      onTextRef.current(queue);
      // Check if code fence was opened/closed in this batch.
      updateCodeFenceState(queue);
      lastTickRef.current = 0;
      return;
    }

    const msPerChar = MS_PER_CHAR[pacing];
    if (!lastTickRef.current) lastTickRef.current = now;
    const elapsed = now - lastTickRef.current;
    let chars = Math.floor(elapsed / msPerChar);
    if (chars < 1) {
      // Not enough time has passed; schedule next frame.
      rafRef.current = requestAnimationFrame(tick);
      return;
    }
    if (chars > CHARS_PER_FRAME_CAP) chars = CHARS_PER_FRAME_CAP;
    if (chars > queue.length) chars = queue.length;

    const slice = queue.slice(0, chars);
    queueRef.current = queue.slice(chars);
    lastTickRef.current = now - (elapsed - chars * msPerChar); // carry remainder

    onTextRef.current(slice);
    updateCodeFenceState(slice);

    if (queueRef.current.length > 0) {
      rafRef.current = requestAnimationFrame(tick);
    } else {
      lastTickRef.current = 0;
    }
  }, []);

  // Toggle codeFenceRef whenever we cross a ``` boundary in the released slice.
  function updateCodeFenceState(slice: string) {
    let i = 0;
    while ((i = slice.indexOf("```", i)) !== -1) {
      codeFenceRef.current = !codeFenceRef.current;
      i += 3;
    }
  }

  const push = useCallback(
    (text: string) => {
      if (!text) return;
      queueRef.current += text;
      // If reduced motion or already in a code block, drain immediately
      // without waiting for rAF — saves up to one frame of perceived latency.
      if (reducedMotionRef.current || codeFenceRef.current) {
        const out = queueRef.current;
        queueRef.current = "";
        onTextRef.current(out);
        updateCodeFenceState(out);
        return;
      }
      if (rafRef.current == null) {
        rafRef.current = requestAnimationFrame(tick);
      }
    },
    [tick],
  );

  const setPacing = useCallback((p: Pacing) => {
    pacingRef.current = p;
  }, []);

  const flush = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    const remaining = queueRef.current;
    queueRef.current = "";
    lastTickRef.current = 0;
    if (remaining) {
      onTextRef.current(remaining);
      updateCodeFenceState(remaining);
    }
  }, []);

  const reset = useCallback(() => {
    if (rafRef.current != null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    queueRef.current = "";
    pacingRef.current = "natural";
    lastTickRef.current = 0;
    codeFenceRef.current = false;
  }, []);

  return { push, setPacing, flush, reset };
}
