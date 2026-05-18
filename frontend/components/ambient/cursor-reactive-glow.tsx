"use client";

import { useEffect } from "react";

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
      const enabled = shouldEnableNeonParallax();
      root.dataset.ambientNeonParallax = enabled ? "true" : "false";
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

      pointer.currentX = lerp(pointer.currentX, pointer.targetX, 0.09);
      pointer.currentY = lerp(pointer.currentY, pointer.targetY, 0.09);

      // Stronger Opera Neon magnetic feel:
      // ring composition center follows the cursor, while the full layer also parallax-shifts.
      const orbitalX = pointer.currentX * 118;
      const orbitalY = pointer.currentY * 88;

      const orbitalFarX = pointer.currentX * 56;
      const orbitalFarY = pointer.currentY * 40;

      // Keep fluid subtle. It should feel like background liquid, not the main moving object.
      const fluidX = pointer.currentX * 4;
      const fluidY = pointer.currentY * 3;

      const tiltX = pointer.currentY * -5;
      const tiltY = pointer.currentX * 7;

      // Move actual gradient center too, not only the entire layer.
      const centerX = 50 + pointer.currentX * 18;
      const centerY = 50 + pointer.currentY * 14;

      const farCenterX = 50 + pointer.currentX * 10;
      const farCenterY = 50 + pointer.currentY * 8;

      root.style.setProperty("--ambient-orbital-x", `${orbitalX}px`);
      root.style.setProperty("--ambient-orbital-y", `${orbitalY}px`);
      root.style.setProperty("--ambient-orbital-far-x", `${orbitalFarX}px`);
      root.style.setProperty("--ambient-orbital-far-y", `${orbitalFarY}px`);
      root.style.setProperty("--ambient-fluid-x", `${fluidX}px`);
      root.style.setProperty("--ambient-fluid-y", `${fluidY}px`);
      root.style.setProperty("--ambient-tilt-x", `${tiltX}deg`);
      root.style.setProperty("--ambient-tilt-y", `${tiltY}deg`);
      root.style.setProperty("--ambient-orbital-center-x", `${centerX}%`);
      root.style.setProperty("--ambient-orbital-center-y", `${centerY}%`);
      root.style.setProperty("--ambient-orbital-far-center-x", `${farCenterX}%`);
      root.style.setProperty("--ambient-orbital-far-center-y", `${farCenterY}%`);

      raf = window.requestAnimationFrame(tick);
    };

    const handlePointerMove = (event: PointerEvent) => {
      updateTargets(event.clientX, event.clientY);
    };

    const handleVisibility = () => {
      running = !document.hidden;

      if (running && !raf) raf = window.requestAnimationFrame(tick);
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

    const interval = window.setInterval(syncEnabled, 700);
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

  return null;
}
