"use client";

import { useEffect, useState } from "react";

const EFFECT_KEY = "assistant.background.effect";
const STYLE_KEY = "assistant.background.style";
const MOTION_KEY = "assistant.background.motion";

function shouldEnableCursorGlow() {
  if (typeof window === "undefined") return false;

  const effect = window.localStorage.getItem(EFFECT_KEY);
  const style = window.localStorage.getItem(STYLE_KEY);
  const motion = window.localStorage.getItem(MOTION_KEY);

  return effect === "fluid-webgl" && style !== "off" && motion !== "false";
}

export function CursorReactiveGlow() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    let frame = 0;

    const syncEnabled = () => {
      setEnabled(shouldEnableCursorGlow());
    };

    const setPointer = (x: number, y: number) => {
      if (frame) window.cancelAnimationFrame(frame);

      frame = window.requestAnimationFrame(() => {
        root.style.setProperty("--ambient-cursor-x", `${x}px`);
        root.style.setProperty("--ambient-cursor-y", `${y}px`);
      });
    };

    const handlePointerMove = (event: PointerEvent) => {
      setPointer(event.clientX, event.clientY);
    };

    const handlePointerLeave = () => {
      root.style.setProperty("--ambient-cursor-opacity", "0");
    };

    const handlePointerEnter = () => {
      root.style.setProperty("--ambient-cursor-opacity", "1");
    };

    syncEnabled();

    root.style.setProperty("--ambient-cursor-x", `${window.innerWidth / 2}px`);
    root.style.setProperty("--ambient-cursor-y", `${window.innerHeight / 2}px`);
    root.style.setProperty("--ambient-cursor-opacity", "1");

    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("pointerleave", handlePointerLeave);
    window.addEventListener("pointerenter", handlePointerEnter);
    window.addEventListener("storage", syncEnabled);

    // LocalStorage changes in the same tab do not fire a storage event,
    // so keep this lightweight sync for Settings changes.
    const interval = window.setInterval(syncEnabled, 700);

    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.clearInterval(interval);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerleave", handlePointerLeave);
      window.removeEventListener("pointerenter", handlePointerEnter);
      window.removeEventListener("storage", syncEnabled);
    };
  }, []);

  return (
    <div
      aria-hidden="true"
      className="ambient-cursor-reactive-glow"
      data-enabled={enabled ? "true" : "false"}
    />
  );
}
