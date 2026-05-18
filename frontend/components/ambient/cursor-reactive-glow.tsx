"use client";

import { useEffect } from "react";

const EFFECT_KEY = "assistant.background.effect";
const STYLE_KEY = "assistant.background.style";
const MOTION_KEY = "assistant.background.motion";

function shouldEnableAmbientMagnetism() {
  if (typeof window === "undefined") return false;

  const effect = window.localStorage.getItem(EFFECT_KEY);
  const style = window.localStorage.getItem(STYLE_KEY);
  const motion = window.localStorage.getItem(MOTION_KEY);

  const effectIsFluid =
    effect === "fluid-webgl" ||
    effect === "fluid" ||
    effect === "fluid-layer" ||
    effect === "fluid-overlay" ||
    Boolean(effect?.includes("fluid"));

  return Boolean(effectIsFluid) && style !== "off" && motion !== "false";
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
      lastX: 0,
      lastY: 0,
      velocity: 0,
    };

    const syncEnabled = () => {
      const enabled = shouldEnableAmbientMagnetism();
      root.dataset.ambientNeonParallax = enabled ? "true" : "false";
    };

    const updateTargets = (clientX: number, clientY: number) => {
      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;

      pointer.targetX = Math.max(-1, Math.min(1, (clientX - centerX) / Math.max(centerX, 1)));
      pointer.targetY = Math.max(-1, Math.min(1, (clientY - centerY) / Math.max(centerY, 1)));
    };

    const tick = () => {
      if (!running) return;

      pointer.currentX = lerp(pointer.currentX, pointer.targetX, 0.12);
      pointer.currentY = lerp(pointer.currentY, pointer.targetY, 0.12);

      const dx = pointer.currentX - pointer.lastX;
      const dy = pointer.currentY - pointer.lastY;
      const rawVelocity = Math.min(1, Math.sqrt(dx * dx + dy * dy) * 18);

      pointer.velocity = lerp(pointer.velocity, rawVelocity, 0.18);
      pointer.lastX = pointer.currentX;
      pointer.lastY = pointer.currentY;

      const x = pointer.currentX;
      const y = pointer.currentY;
      const v = pointer.velocity;

      root.style.setProperty("--ambient-magnet-x", `${x * 110}px`);
      root.style.setProperty("--ambient-magnet-y", `${y * 82}px`);
      root.style.setProperty("--ambient-magnet-far-x", `${x * 64}px`);
      root.style.setProperty("--ambient-magnet-far-y", `${y * 46}px`);
      root.style.setProperty("--ambient-magnet-speed", `${1 + v * 0.55}`);
      root.style.setProperty("--ambient-magnet-scale", `${1 + v * 0.01}`);
      root.style.setProperty("--ambient-magnet-blur", `${v * 0.12}px`);

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
