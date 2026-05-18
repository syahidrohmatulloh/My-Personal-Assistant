#!/usr/bin/env python3
"""Clean up My Personal Assistant ambient background CSS.

Run from repo root:
  python3 ambient_cleanup_patch.py

It will:
- create frontend/components/ambient/ambient-background.css
- rewrite frontend/components/ambient/cursor-reactive-glow.tsx as a CSS-variable controller only
- import the ambient CSS and controller from frontend/app/layout.tsx
- remove duplicated/old ambient CSS experiment blocks from frontend/app/globals.css
- create .before-ambient-cleanup backups for changed files
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path.cwd()
FRONTEND = ROOT / "frontend"
GLOBALS = FRONTEND / "app" / "globals.css"
LAYOUT = FRONTEND / "app" / "layout.tsx"
AMBIENT_CSS = FRONTEND / "components" / "ambient" / "ambient-background.css"
CURSOR = FRONTEND / "components" / "ambient" / "cursor-reactive-glow.tsx"

AMBIENT_KEYWORDS = (
    "ambient-background",
    "ambient-layer",
    "ambient-style-",
    "ambient-readability-vignette",
    "ambient-mood-based",
    "ambient-palette-",
    "ambient-intensity-",
    "ambient-static",
    "cosmic-fluid-mount",
    "cosmic-fluid-canvas",
    "ambient-opera-neon",
    "ambient-cursor-reactive-glow",
    "ambient-magnet",
    "ambient-object-",
    "ambient-pointer-",
    "data-ambient-neon-parallax",
)

AMBIENT_CSS_CONTENT = r'''/* ===========================================================================
   Ambient Background
   Clean structure: visible objects are .ambient-layer-a/b/c, not ::before/::after.
   =========================================================================== */

/* ---------------------------------------------------------------------------
   Base container
--------------------------------------------------------------------------- */

.ambient-background {
  --ambient-magnet-x: 0px;
  --ambient-magnet-y: 0px;
  --ambient-magnet-far-x: 0px;
  --ambient-magnet-far-y: 0px;
  --ambient-magnet-speed: 1;
  --ambient-magnet-scale: 1;
  --ambient-magnet-blur: 0px;

  position: fixed;
  inset: 0;
  overflow: hidden;
  pointer-events: none;
  z-index: 0 !important;
  contain: layout paint style;
  opacity: 0.82;
  background:
    radial-gradient(circle at 50% 0%, rgb(var(--accent) / 0.05), transparent 34%),
    linear-gradient(135deg, rgb(var(--bg-deep)) 0%, rgb(var(--bg)) 52%, rgb(var(--bg-deep)) 100%);
}

.ambient-background.ambient-intensity-low { opacity: 0.58; }
.ambient-background.ambient-intensity-medium { opacity: 0.86; }

/* ---------------------------------------------------------------------------
   Shared layer setup
--------------------------------------------------------------------------- */

.ambient-layer,
.ambient-readability-vignette {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.ambient-layer {
  transform: translateZ(0);
  will-change: transform, translate, opacity, filter;
}

.ambient-readability-vignette {
  z-index: 4;
  background:
    radial-gradient(circle at 50% 35%, transparent 0%, rgb(var(--bg-deep) / 0.05) 58%, rgb(var(--bg-deep) / 0.18) 100%),
    linear-gradient(to bottom, rgb(var(--bg-deep) / 0.1), transparent 18%, transparent 78%, rgb(var(--bg-deep) / 0.12));
}

@keyframes ambient-drift {
  0% { transform: translate3d(-1.5%, -1%, 0) scale(1) rotate(0deg); }
  50% { transform: translate3d(1.5%, 1%, 0) scale(1.04) rotate(3deg); }
  100% { transform: translate3d(-1.5%, -1%, 0) scale(1) rotate(0deg); }
}

@keyframes ambient-slow-spin {
  from { transform: translate3d(0, 0, 0) rotate(0deg); }
  to { transform: translate3d(0, 0, 0) rotate(360deg); }
}

@keyframes ambient-flow {
  0% { transform: translate3d(-2%, 0, 0); background-position: 0 0, 0 0; }
  50% { transform: translate3d(2%, -1%, 0); background-position: 52px 18px, -34px 22px; }
  100% { transform: translate3d(-2%, 0, 0); background-position: 0 0, 0 0; }
}

@keyframes ambient-wave {
  0% { transform: translate3d(-2%, 0, 0) scaleX(1); filter: blur(1px); }
  50% { transform: translate3d(2%, -0.5%, 0) scaleX(1.04); filter: blur(1.5px); }
  100% { transform: translate3d(-2%, 0, 0) scaleX(1); filter: blur(1px); }
}

/* ---------------------------------------------------------------------------
   Style variants
--------------------------------------------------------------------------- */

/* Cosmic Plasma */
.ambient-style-cosmic-plasma .ambient-layer-a {
  left: 18%;
  top: 7%;
  width: 42vw;
  height: 30vw;
  min-width: 420px;
  min-height: 290px;
  border-radius: 48% 52% 58% 42% / 58% 44% 56% 42%;
  border: 1.5px solid rgb(var(--accent) / 0.42);
  box-shadow:
    0 0 42px rgb(var(--accent) / 0.16),
    inset 0 0 40px rgb(168 85 247 / 0.14),
    18px 10px 34px rgb(56 189 248 / 0.10),
    -18px -10px 34px rgb(217 70 239 / 0.10);
  filter: blur(0.2px);
  transform: rotate(-18deg);
  animation: ambient-drift 28s ease-in-out infinite;
}

.ambient-style-cosmic-plasma .ambient-layer-b {
  background:
    radial-gradient(ellipse at 25% 40%, rgb(217 70 239 / 0.12), transparent 34%),
    radial-gradient(ellipse at 58% 55%, rgb(56 189 248 / 0.10), transparent 34%),
    radial-gradient(ellipse at 45% 20%, rgb(var(--accent) / 0.10), transparent 32%);
  filter: blur(42px);
  animation: ambient-drift 34s ease-in-out infinite reverse;
}

.ambient-style-cosmic-plasma .ambient-layer-c { opacity: 0; }

/* Nebula Drift */
.ambient-style-nebula-drift .ambient-layer-a {
  background:
    radial-gradient(ellipse at 18% 64%, rgb(var(--orb-1)), transparent 38%),
    radial-gradient(ellipse at 48% 38%, rgb(var(--orb-2)), transparent 40%),
    radial-gradient(ellipse at 78% 55%, rgb(var(--orb-3)), transparent 38%);
  filter: blur(72px);
  animation: ambient-drift 38s ease-in-out infinite;
}

.ambient-style-nebula-drift .ambient-layer-b {
  background:
    linear-gradient(115deg, transparent 0%, rgb(56 189 248 / 0.08) 38%, rgb(168 85 247 / 0.07) 54%, transparent 75%);
  filter: blur(38px);
  opacity: 0.8;
  animation: ambient-flow 44s ease-in-out infinite;
}

.ambient-style-nebula-drift .ambient-layer-c { opacity: 0; }

/* Micro Particle Flow */
.ambient-style-micro-particle-flow .ambient-layer-a {
  background-image:
    radial-gradient(circle, rgb(var(--accent) / 0.24) 0 1px, transparent 1.4px),
    radial-gradient(circle, rgb(56 189 248 / 0.14) 0 1px, transparent 1.5px);
  background-size: 34px 34px, 56px 56px;
  mask-image: linear-gradient(to bottom, transparent 0%, black 24%, black 72%, transparent 100%);
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, black 24%, black 72%, transparent 100%);
  opacity: 0.45;
  animation: ambient-flow 36s ease-in-out infinite;
}

.ambient-style-micro-particle-flow .ambient-layer-b {
  background:
    radial-gradient(ellipse at 20% 52%, rgb(217 70 239 / 0.08), transparent 34%),
    radial-gradient(ellipse at 72% 46%, rgb(56 189 248 / 0.08), transparent 34%);
  filter: blur(55px);
}

.ambient-style-micro-particle-flow .ambient-layer-c { opacity: 0; }

/* Orbital Rings */
.ambient-style-orbital-rings .ambient-layer-a,
.ambient-style-orbital-rings .ambient-layer-b {
  left: 32%;
  top: 18%;
  width: 38vw;
  height: 18vw;
  min-width: 380px;
  min-height: 180px;
  border-radius: 50%;
  border: 1px solid rgb(var(--accent) / 0.26);
  box-shadow:
    0 0 26px rgb(var(--accent) / 0.10),
    inset 0 0 22px rgb(56 189 248 / 0.06);
  transform: rotate(-12deg);
  animation: ambient-slow-spin 52s linear infinite;
}

.ambient-style-orbital-rings .ambient-layer-b {
  width: 46vw;
  height: 23vw;
  border-color: rgb(168 85 247 / 0.20);
  animation-duration: 74s;
  animation-direction: reverse;
}

.ambient-style-orbital-rings .ambient-layer-c {
  background:
    radial-gradient(circle at 55% 44%, rgb(var(--accent) / 0.16), transparent 9%),
    radial-gradient(circle at 24% 66%, rgb(168 85 247 / 0.12), transparent 8%);
  filter: blur(28px);
  animation: ambient-drift 36s ease-in-out infinite;
}

/* Voice Wave */
.ambient-style-voice-wave .ambient-layer-a {
  top: 30%;
  height: 42%;
  background:
    radial-gradient(ellipse at 18% 50%, rgb(var(--accent) / 0.18), transparent 22%),
    radial-gradient(ellipse at 48% 50%, rgb(56 189 248 / 0.14), transparent 28%),
    radial-gradient(ellipse at 82% 50%, rgb(217 70 239 / 0.15), transparent 22%);
  mask-image: repeating-radial-gradient(ellipse at center, black 0 1px, transparent 2px 8px);
  -webkit-mask-image: repeating-radial-gradient(ellipse at center, black 0 1px, transparent 2px 8px);
  animation: ambient-wave 14s ease-in-out infinite;
}

.ambient-style-voice-wave .ambient-layer-b {
  top: 37%;
  height: 26%;
  background: linear-gradient(90deg, transparent 7%, rgb(var(--accent) / 0.22), rgb(56 189 248 / 0.12), rgb(217 70 239 / 0.18), transparent 93%);
  clip-path: polygon(0% 50%, 8% 44%, 16% 58%, 24% 38%, 32% 63%, 40% 44%, 48% 56%, 56% 42%, 64% 61%, 72% 46%, 80% 55%, 88% 47%, 100% 50%, 100% 70%, 0% 70%);
  filter: blur(8px);
  opacity: 0.75;
  animation: ambient-wave 12s ease-in-out infinite reverse;
}

.ambient-style-voice-wave .ambient-layer-c { opacity: 0; }

.ambient-background.ambient-intensity-low .ambient-layer-a,
.ambient-background.ambient-intensity-low .ambient-layer-b,
.ambient-background.ambient-intensity-low .ambient-layer-c { opacity: 0.74; }

.ambient-background.ambient-intensity-medium .ambient-layer-a,
.ambient-background.ambient-intensity-medium .ambient-layer-b,
.ambient-background.ambient-intensity-medium .ambient-layer-c { opacity: 1; }

.ambient-background.ambient-static .ambient-layer,
.ambient-background.ambient-static .ambient-readability-vignette { animation: none !important; }

/* ---------------------------------------------------------------------------
   Mood palettes
--------------------------------------------------------------------------- */

.ambient-background {
  --ambient-primary: var(--accent);
  --ambient-orb-1: var(--orb-1);
  --ambient-orb-2: var(--orb-2);
  --ambient-orb-3: var(--orb-3);
}

.ambient-background.ambient-palette-calm-blue {
  --accent: 56 189 248;
  --orb-1: 56 189 248 / 0.16;
  --orb-2: 16 185 129 / 0.12;
  --orb-3: 234 179 8 / 0.08;
}

.ambient-background.ambient-palette-warm-pink {
  --accent: 236 72 153;
  --orb-1: 236 72 153 / 0.16;
  --orb-2: 251 146 60 / 0.10;
  --orb-3: 250 204 21 / 0.08;
}

.ambient-background.ambient-palette-focus-cyan {
  --accent: 34 211 238;
  --orb-1: 34 211 238 / 0.14;
  --orb-2: 59 130 246 / 0.12;
  --orb-3: 15 23 42 / 0.06;
}

.ambient-background.ambient-palette-reflective-indigo {
  --accent: 139 92 246;
  --orb-1: 139 92 246 / 0.16;
  --orb-2: 79 70 229 / 0.12;
  --orb-3: 56 189 248 / 0.07;
}

.ambient-background.ambient-palette-calm-teal {
  --accent: 20 184 166;
  --orb-1: 20 184 166 / 0.14;
  --orb-2: 45 212 191 / 0.10;
  --orb-3: 56 189 248 / 0.08;
}

.ambient-background.ambient-palette-muted-amber {
  --accent: 245 158 11;
  --orb-1: 245 158 11 / 0.12;
  --orb-2: 239 68 68 / 0.07;
  --orb-3: 20 184 166 / 0.06;
}

.ambient-background.ambient-mood-based::after {
  content: "";
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 3;
  opacity: 0.46;
  background:
    radial-gradient(circle at 22% 18%, rgb(var(--orb-1)), transparent 34%),
    radial-gradient(circle at 78% 72%, rgb(var(--orb-2)), transparent 38%),
    radial-gradient(circle at 50% 42%, rgb(var(--orb-3)), transparent 46%);
  filter: blur(52px);
  animation: ambient-drift 34s ease-in-out infinite;
}

/* ---------------------------------------------------------------------------
   Fluid layer
--------------------------------------------------------------------------- */

.cosmic-fluid-mount {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  overflow: hidden;
  opacity: 0.14;
  mix-blend-mode: screen;
}

.cosmic-fluid-canvas {
  width: 100%;
  height: 100%;
  display: block;
  opacity: 0.78;
  filter: blur(20px) saturate(1.06);
}

.ambient-background.ambient-intensity-low .cosmic-fluid-mount { opacity: 0.08; }
.ambient-background.ambient-intensity-medium .cosmic-fluid-mount { opacity: 0.14; }
.ambient-background.ambient-intensity-low .cosmic-fluid-canvas { opacity: 0.55; }
.ambient-background.ambient-intensity-medium .cosmic-fluid-canvas { opacity: 0.82; }

html[data-ambient-neon-parallax="true"] .ambient-background .cosmic-fluid-mount,
html[data-ambient-neon-parallax="true"] .cosmic-fluid-mount {
  opacity: 0.055 !important;
  filter: blur(34px) saturate(0.88) contrast(0.9) !important;
  transform: scale(1.004) !important;
  mix-blend-mode: multiply !important;
}

/* ---------------------------------------------------------------------------
   Cursor magnetism
   Controller only sets CSS variables. This CSS moves existing layers only.
--------------------------------------------------------------------------- */

html[data-ambient-neon-parallax="true"] .ambient-background .ambient-layer-a {
  translate:
    calc(var(--ambient-magnet-x) * 0.42)
    calc(var(--ambient-magnet-y) * 0.34);
  scale: var(--ambient-magnet-scale);
  animation-duration: calc(32s / var(--ambient-magnet-speed)) !important;
  filter: blur(var(--ambient-magnet-blur)) saturate(1.06);
}

html[data-ambient-neon-parallax="true"] .ambient-background .ambient-layer-b {
  translate:
    calc(var(--ambient-magnet-far-x) * 0.28)
    calc(var(--ambient-magnet-far-y) * 0.24);
  scale: calc(var(--ambient-magnet-scale) * 0.997);
  animation-duration: calc(42s / var(--ambient-magnet-speed)) !important;
}

html[data-ambient-neon-parallax="true"] .ambient-background .ambient-layer-c {
  translate:
    calc(var(--ambient-magnet-x) * 0.12)
    calc(var(--ambient-magnet-y) * 0.10);
  scale: 1;
}

/* Orbital rings are intentionally more conservative to avoid dizziness. */
html[data-ambient-neon-parallax="true"] .ambient-background.ambient-style-orbital-rings .ambient-layer-a {
  translate:
    calc(var(--ambient-magnet-x) * 0.12)
    calc(var(--ambient-magnet-y) * 0.10);
  scale: 1.006;
  animation-duration: 58s !important;
  filter: blur(0.04px) saturate(1.04) !important;
}

html[data-ambient-neon-parallax="true"] .ambient-background.ambient-style-orbital-rings .ambient-layer-b {
  translate:
    calc(var(--ambient-magnet-far-x) * 0.18)
    calc(var(--ambient-magnet-far-y) * 0.15);
  scale: 1.003;
  animation-duration: 82s !important;
  filter: blur(0.03px) saturate(1.03) !important;
}

html[data-ambient-neon-parallax="true"] .ambient-background.ambient-style-orbital-rings .ambient-layer-c {
  translate:
    calc(var(--ambient-magnet-x) * 0.05)
    calc(var(--ambient-magnet-y) * 0.04);
  scale: 1;
}

/* ---------------------------------------------------------------------------
   Responsive / reduced motion
--------------------------------------------------------------------------- */

@media (max-width: 640px) {
  .ambient-background { opacity: 0.48; }

  .ambient-style-cosmic-plasma .ambient-layer-a,
  .ambient-style-orbital-rings .ambient-layer-a,
  .ambient-style-orbital-rings .ambient-layer-b {
    left: 8%;
    width: 86vw;
    height: 52vw;
    min-width: 0;
    min-height: 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .ambient-background .ambient-layer,
  .ambient-background .ambient-readability-vignette,
  .ambient-background.ambient-mood-based::after {
    animation: none !important;
    translate: none !important;
    scale: none !important;
  }

  html[data-ambient-neon-parallax="true"] .ambient-background .ambient-layer-a,
  html[data-ambient-neon-parallax="true"] .ambient-background .ambient-layer-b,
  html[data-ambient-neon-parallax="true"] .ambient-background .ambient-layer-c {
    translate: none !important;
    scale: none !important;
  }
}

/* Hard kill old wrong visual experiments if cached CSS still exists briefly. */
.ambient-opera-neon-field,
.ambient-opera-neon-canvas,
.ambient-cursor-reactive-glow {
  display: none !important;
  opacity: 0 !important;
  visibility: hidden !important;
  pointer-events: none !important;
}
'''

CURSOR_TSX_CONTENT = r'''"use client";

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
'''


def backup(path: Path) -> None:
    if path.exists():
        backup_path = path.with_name(path.name + ".before-ambient-cleanup")
        backup_path.write_text(path.read_text())
        print(f"Backup: {backup_path}")


def find_matching_brace(text: str, open_index: int) -> int:
    depth = 0
    in_string: str | None = None
    escape = False
    i = open_index
    while i < len(text):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == in_string:
                in_string = None
        else:
            if ch in ('"', "'"):
                in_string = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    return len(text)


def strip_ambient_blocks(css: str) -> str:
    """Remove top-level CSS blocks that belong to ambient background experiments."""
    out: list[str] = []
    i = 0
    n = len(css)

    while i < n:
        brace = css.find("{", i)
        if brace == -1:
            out.append(css[i:])
            break

        # Keep text before this block temporarily; may include whitespace/comments.
        prefix = css[i:brace]
        selector_start = max(prefix.rfind("}"), prefix.rfind("/*"))
        selector = prefix[selector_start + 1 :].strip() if selector_start != -1 else prefix.strip()
        block_end = find_matching_brace(css, brace)
        block = css[i:block_end]
        selector_and_block = css[max(0, i):block_end]

        lower = selector_and_block.lower()
        should_remove = False

        if "@keyframes ambient-" in selector.lower():
            should_remove = True
        elif any(keyword in lower for keyword in AMBIENT_KEYWORDS):
            should_remove = True
        elif selector.strip().startswith(":root") and "--ambient-" in lower:
            should_remove = True

        if should_remove:
            # Remove directly preceding ambient-only comments too.
            if out:
                joined = "".join(out)
                comment_start = joined.rfind("/*")
                comment_end = joined.rfind("*/")
                if comment_start != -1 and (comment_end == -1 or comment_end < comment_start):
                    out = [joined[:comment_start].rstrip(), "\n\n"]
            if not out or not "".join(out).endswith("\n"):
                out.append("\n")
        else:
            out.append(block)

        i = block_end

    cleaned = "".join(out)
    # Remove leftover empty Opera/ambient section comments.
    cleaned = re.sub(r"/\*[-\s\n]*(?:Opera Neon|Ambient cursor|FINAL: Ambient|Fix cursor|Final override)[\s\S]*?\*/", "\n", cleaned, flags=re.I)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.rstrip() + "\n"


def ensure_layout_imports(layout_text: str) -> str:
    if '"@/components/ambient/ambient-background.css"' not in layout_text and "'@/components/ambient/ambient-background.css'" not in layout_text:
        layout_text = layout_text.replace('import "./globals.css";\n', 'import "./globals.css";\nimport "@/components/ambient/ambient-background.css";\n')

    if 'cursor-reactive-glow' not in layout_text:
        layout_text = layout_text.replace(
            'import { AmbientBackground } from "@/components/ambient/ambient-background";\n',
            'import { AmbientBackground } from "@/components/ambient/ambient-background";\nimport { CursorReactiveGlow } from "@/components/ambient/cursor-reactive-glow";\n',
        )

    if "<CursorReactiveGlow />" not in layout_text:
        layout_text = layout_text.replace("        <AmbientBackground />\n", "        <AmbientBackground />\n        <CursorReactiveGlow />\n")

    return layout_text


def main() -> None:
    missing = [p for p in (GLOBALS, LAYOUT) if not p.exists()]
    if missing:
        raise SystemExit("Missing expected file(s): " + ", ".join(str(p) for p in missing))

    AMBIENT_CSS.parent.mkdir(parents=True, exist_ok=True)
    CURSOR.parent.mkdir(parents=True, exist_ok=True)

    backup(GLOBALS)
    backup(LAYOUT)
    backup(AMBIENT_CSS)
    backup(CURSOR)

    globals_text = GLOBALS.read_text()
    GLOBALS.write_text(strip_ambient_blocks(globals_text))

    AMBIENT_CSS.write_text(AMBIENT_CSS_CONTENT.strip() + "\n")
    CURSOR.write_text(CURSOR_TSX_CONTENT.strip() + "\n")

    layout_text = LAYOUT.read_text()
    LAYOUT.write_text(ensure_layout_imports(layout_text))

    print("\nDone. Changed:")
    print(f"- {GLOBALS}")
    print(f"- {LAYOUT}")
    print(f"- {AMBIENT_CSS}")
    print(f"- {CURSOR}")
    print("\nNext:")
    print("  rm -rf frontend/.next")
    print("  pnpm --dir frontend build")


if __name__ == "__main__":
    main()
