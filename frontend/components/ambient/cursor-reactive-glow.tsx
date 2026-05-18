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

      root.style.setProperty("--ambient-pointer-x", `${clientX}px`);
      root.style.setProperty("--ambient-pointer-y", `${clientY}px`);
    };

    const tick = () => {
      if (!running) return;

      pointer.currentX = lerp(pointer.currentX, pointer.targetX, 0.11);
      pointer.currentY = lerp(pointer.currentY, pointer.targetY, 0.11);

      const dx = pointer.currentX - pointer.lastX;
      const dy = pointer.currentY - pointer.lastY;
      const rawVelocity = Math.min(1, Math.sqrt(dx * dx + dy * dy) * 18);

      pointer.velocity = lerp(pointer.velocity, rawVelocity, 0.18);
      pointer.lastX = pointer.currentX;
      pointer.lastY = pointer.currentY;

      const x = pointer.currentX;
      const y = pointer.currentY;
      const v = pointer.velocity;

      // Move the internal composition center toward cursor.
      root.style.setProperty("--ambient-object-center-x", `${50 + x * 24}%`);
      root.style.setProperty("--ambient-object-center-y", `${50 + y * 20}%`);
      root.style.setProperty("--ambient-object-far-center-x", `${50 + x * 12}%`);
      root.style.setProperty("--ambient-object-far-center-y", `${50 + y * 10}%`);

      // Move the existing background object itself.
      root.style.setProperty("--ambient-object-x", `${x * 78}px`);
      root.style.setProperty("--ambient-object-y", `${y * 58}px`);
      root.style.setProperty("--ambient-object-far-x", `${x * 34}px`);
      root.style.setProperty("--ambient-object-far-y", `${y * 26}px`);

      // Cursor movement temporarily speeds up / disturbs the object.
      root.style.setProperty("--ambient-object-speed", `${1 + v * 1.8}`);
      root.style.setProperty("--ambient-object-pulse", `${1 + v * 0.08}`);
      root.style.setProperty("--ambient-object-blur", `${0.1 + v * 0.7}px`);

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
