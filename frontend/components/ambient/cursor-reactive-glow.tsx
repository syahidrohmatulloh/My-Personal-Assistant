"use client";

import { useEffect, useState } from "react";

const EFFECT_KEY = "assistant.background.effect";
const STYLE_KEY = "assistant.background.style";
const MOTION_KEY = "assistant.background.motion";

function shouldEnableNeonParallax() {
  if (typeof window === "undefined") return false;

  const effect = window.localStorage.getItem(EFFECT_KEY);
  const style = window.localStorage.getItem(STYLE_KEY);
  const motion = window.localStorage.getItem(MOTION_KEY);

  return effect === "fluid-webgl" && style !== "off" && motion !== "false";
}

function lerp(current: number, target: number, factor: number) {
  return current + (target - current) * factor;
}

export function CursorReactiveGlow() {
  const [enabled, setEnabled] = useState(false);

  useEffect(() => {
    const root = document.documentElement;

    let raf = 0;
    let running = true;

    const pointer = {
      targetX: 0,
      targetY: 0,
      currentX: 0,
      currentY: 0,
    };

    const syncEnabled = () => {
      const nextEnabled = shouldEnableNeonParallax();
      setEnabled(nextEnabled);
      root.dataset.ambientNeonParallax = nextEnabled ? "true" : "false";
    };

    const updateTargets = (clientX: number, clientY: number) => {
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;

      const normalizedX = (clientX - centerX) / Math.max(centerX, 1);
      const normalizedY = (clientY - centerY) / Math.max(centerY, 1);

      pointer.targetX = Math.max(-1, Math.min(1, normalizedX));
      pointer.targetY = Math.max(-1, Math.min(1, normalizedY));

      root.style.setProperty("--ambient-pointer-x", `${clientX}px`);
      root.style.setProperty("--ambient-pointer-y", `${clientY}px`);
    };

    const tick = () => {
      if (!running) return;

      pointer.currentX = lerp(pointer.currentX, pointer.targetX, 0.075);
      pointer.currentY = lerp(pointer.currentY, pointer.targetY, 0.075);

      const orbitalX = pointer.currentX * 34;
      const orbitalY = pointer.currentY * 26;

      const orbitalFarX = pointer.currentX * -18;
      const orbitalFarY = pointer.currentY * -14;

      const fluidX = pointer.currentX * 10;
      const fluidY = pointer.currentY * 8;

      root.style.setProperty("--ambient-orbital-x", `${orbitalX}px`);
      root.style.setProperty("--ambient-orbital-y", `${orbitalY}px`);
      root.style.setProperty("--ambient-orbital-far-x", `${orbitalFarX}px`);
      root.style.setProperty("--ambient-orbital-far-y", `${orbitalFarY}px`);
      root.style.setProperty("--ambient-fluid-x", `${fluidX}px`);
      root.style.setProperty("--ambient-fluid-y", `${fluidY}px`);

      raf = window.requestAnimationFrame(tick);
    };

    const handlePointerMove = (event: PointerEvent) => {
      updateTargets(event.clientX, event.clientY);
    };

    const handleVisibility = () => {
      running = !document.hidden;

      if (running && !raf) {
        raf = window.requestAnimationFrame(tick);
      }

      if (!running && raf) {
        window.cancelAnimationFrame(raf);
        raf = 0;
      }
    };

    syncEnabled();
    updateTargets(window.innerWidth / 2, window.innerHeight / 2);

    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("storage", syncEnabled);
    document.addEventListener("visibilitychange", handleVisibility);

    const interval = window.setInterval(syncEnabled, 600);
    raf = window.requestAnimationFrame(tick);

    return () => {
      running = false;
      if (raf) window.cancelAnimationFrame(raf);
      window.clearInterval(interval);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("storage", syncEnabled);
      document.removeEventListener("visibilitychange", handleVisibility);
      delete root.dataset.ambientNeonParallax;
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
