"use client";

import { useEffect, useRef } from "react";

const EFFECT_KEY = "assistant.background.effect";
const STYLE_KEY = "assistant.background.style";
const MOTION_KEY = "assistant.background.motion";

type Particle = {
  angle: number;
  radius: number;
  size: number;
  alpha: number;
  speed: number;
  wobble: number;
  wobbleSpeed: number;
};

function shouldEnableOperaNeonField() {
  if (typeof window === "undefined") return false;

  const effect = window.localStorage.getItem(EFFECT_KEY);
  const style = window.localStorage.getItem(STYLE_KEY);
  const motion = window.localStorage.getItem(MOTION_KEY);

  return effect === "fluid-webgl" && style !== "off" && motion !== "false";
}

function lerp(current: number, target: number, factor: number) {
  return current + (target - current) * factor;
}

function createParticles(count: number): Particle[] {
  return Array.from({ length: count }, () => {
    // Dense ring distribution, like Opera Neon particle cloud.
    const radius = 0.42 + Math.pow(Math.random(), 0.75) * 0.75;

    return {
      angle: Math.random() * Math.PI * 2,
      radius,
      size: 0.45 + Math.random() * 1.35,
      alpha: 0.045 + Math.random() * 0.18,
      speed: (Math.random() - 0.5) * 0.0016,
      wobble: Math.random() * Math.PI * 2,
      wobbleSpeed: 0.006 + Math.random() * 0.01,
    };
  });
}

export function CursorReactiveGlow() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const root = document.documentElement;
    const canvas = canvasRef.current;
    if (!canvas) return;

    const ctx = canvas.getContext("2d", { alpha: true });
    if (!ctx) return;

    let enabled = shouldEnableOperaNeonField();
    let raf = 0;
    let running = true;

    const particles = createParticles(1700);

    const pointer = {
      targetX: window.innerWidth * 0.5,
      targetY: window.innerHeight * 0.5,
      currentX: window.innerWidth * 0.5,
      currentY: window.innerHeight * 0.5,
      normalizedX: 0,
      normalizedY: 0,
    };

    const resize = () => {
      const dpr = Math.min(window.devicePixelRatio || 1, 1.6);
      canvas.width = Math.floor(window.innerWidth * dpr);
      canvas.height = Math.floor(window.innerHeight * dpr);
      canvas.style.width = `${window.innerWidth}px`;
      canvas.style.height = `${window.innerHeight}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const syncEnabled = () => {
      enabled = shouldEnableOperaNeonField();
      root.dataset.ambientNeonParallax = enabled ? "true" : "false";
    };

    const updatePointer = (clientX: number, clientY: number) => {
      pointer.targetX = clientX;
      pointer.targetY = clientY;

      const centerX = window.innerWidth / 2;
      const centerY = window.innerHeight / 2;

      pointer.normalizedX = Math.max(-1, Math.min(1, (clientX - centerX) / Math.max(centerX, 1)));
      pointer.normalizedY = Math.max(-1, Math.min(1, (clientY - centerY) / Math.max(centerY, 1)));

      root.style.setProperty("--ambient-pointer-x", `${clientX}px`);
      root.style.setProperty("--ambient-pointer-y", `${clientY}px`);
    };

    const draw = () => {
      if (!running) return;

      pointer.currentX = lerp(pointer.currentX, pointer.targetX, 0.065);
      pointer.currentY = lerp(pointer.currentY, pointer.targetY, 0.065);

      const nx = pointer.normalizedX;
      const ny = pointer.normalizedY;

      root.style.setProperty("--ambient-orbital-x", `${nx * 130}px`);
      root.style.setProperty("--ambient-orbital-y", `${ny * 96}px`);
      root.style.setProperty("--ambient-orbital-far-x", `${nx * 64}px`);
      root.style.setProperty("--ambient-orbital-far-y", `${ny * 46}px`);
      root.style.setProperty("--ambient-fluid-x", `${nx * 3}px`);
      root.style.setProperty("--ambient-fluid-y", `${ny * 2}px`);
      root.style.setProperty("--ambient-tilt-x", `${ny * -5}deg`);
      root.style.setProperty("--ambient-tilt-y", `${nx * 7}deg`);
      root.style.setProperty("--ambient-orbital-center-x", `${50 + nx * 30}%`);
      root.style.setProperty("--ambient-orbital-center-y", `${50 + ny * 24}%`);
      root.style.setProperty("--ambient-orbital-far-center-x", `${50 + nx * 17}%`);
      root.style.setProperty("--ambient-orbital-far-center-y", `${50 + ny * 13}%`);

      ctx.clearRect(0, 0, window.innerWidth, window.innerHeight);

      if (enabled) {
        const minSide = Math.min(window.innerWidth, window.innerHeight);

        // Large soft particle ellipse centered on cursor.
        const scaleX = minSide * 0.48;
        const scaleY = minSide * 0.34;

        ctx.save();
        ctx.globalCompositeOperation = "multiply";

        for (const p of particles) {
          p.angle += p.speed;
          p.wobble += p.wobbleSpeed;

          const wobble = Math.sin(p.wobble) * 0.035;
          const r = p.radius + wobble;

          const x = pointer.currentX + Math.cos(p.angle) * r * scaleX;
          const y = pointer.currentY + Math.sin(p.angle) * r * scaleY;

          // Fade outer particles for soft cloudy edge.
          const edgeFade = Math.max(0, Math.min(1, 1.2 - Math.abs(r - 0.78)));
          const alpha = p.alpha * edgeFade;

          ctx.globalAlpha = alpha;
          ctx.fillStyle = "rgb(18 18 18)";
          ctx.beginPath();
          ctx.arc(x, y, p.size, 0, Math.PI * 2);
          ctx.fill();
        }

        // Very soft inner shadow so it reads as a cloud/ring mass.
        const gradient = ctx.createRadialGradient(
          pointer.currentX,
          pointer.currentY,
          minSide * 0.12,
          pointer.currentX,
          pointer.currentY,
          minSide * 0.54,
        );
        gradient.addColorStop(0, "rgba(0,0,0,0)");
        gradient.addColorStop(0.38, "rgba(0,0,0,0.07)");
        gradient.addColorStop(0.7, "rgba(0,0,0,0.12)");
        gradient.addColorStop(1, "rgba(0,0,0,0)");

        ctx.globalAlpha = 1;
        ctx.fillStyle = gradient;
        ctx.fillRect(0, 0, window.innerWidth, window.innerHeight);

        ctx.restore();
      }

      raf = window.requestAnimationFrame(draw);
    };

    const handlePointerMove = (event: PointerEvent) => {
      updatePointer(event.clientX, event.clientY);
    };

    const handleVisibility = () => {
      running = !document.hidden;

      if (running && !raf) {
        raf = window.requestAnimationFrame(draw);
      }

      if (!running && raf) {
        window.cancelAnimationFrame(raf);
        raf = 0;
      }
    };

    resize();
    syncEnabled();
    updatePointer(window.innerWidth / 2, window.innerHeight / 2);

    window.addEventListener("resize", resize);
    window.addEventListener("pointermove", handlePointerMove, { passive: true });
    window.addEventListener("storage", syncEnabled);
    document.addEventListener("visibilitychange", handleVisibility);

    const interval = window.setInterval(syncEnabled, 700);
    raf = window.requestAnimationFrame(draw);

    return () => {
      running = false;
      if (raf) window.cancelAnimationFrame(raf);
      window.clearInterval(interval);
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("storage", syncEnabled);
      document.removeEventListener("visibilitychange", handleVisibility);
      delete root.dataset.ambientNeonParallax;
    };
  }, []);

  return (
    <div aria-hidden="true" className="ambient-opera-neon-field">
      <canvas ref={canvasRef} className="ambient-opera-neon-canvas" />
    </div>
  );
}
