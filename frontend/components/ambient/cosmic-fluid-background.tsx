"use client";

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import type {
  BackgroundIntensity,
  BackgroundPalette,
} from "@/lib/ambient-background";

const vertexShader = `
  void main() {
    gl_Position = vec4(position, 1.0);
  }
`;

const fragmentShader = `
  precision highp float;

  uniform float uTime;
  uniform vec2 uResolution;
  uniform vec3 uColorA;
  uniform vec3 uColorB;
  uniform vec3 uColorC;
  uniform float uIntensity;

  float hash(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);

    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));

    return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
  }

  float fbm(vec2 p) {
    float v = 0.0;
    float amp = 0.5;
    for (int i = 0; i < 5; i++) {
      v += amp * noise(p);
      p = p * 2.03 + vec2(17.13, 9.21);
      amp *= 0.5;
    }
    return v;
  }

  void main() {
    vec2 uv = gl_FragCoord.xy / max(uResolution.xy, vec2(1.0));
    vec2 centered = uv - 0.5;
    centered.x *= uResolution.x / max(uResolution.y, 1.0);

    float t = uTime * 0.055;
    float slow = uTime * 0.018;

    vec2 flow = centered;
    flow += 0.10 * vec2(
      sin(centered.y * 3.1 + slow),
      cos(centered.x * 2.7 - slow)
    );

    float n1 = fbm(flow * 2.25 + vec2(t, -t * 0.75));
    float n2 = fbm(flow * 3.20 - vec2(t * 0.45, t * 0.55));
    float n3 = fbm(flow * 5.00 + vec2(sin(t), cos(t)));

    float fluid = smoothstep(0.18, 0.92, n1 * 0.58 + n2 * 0.34 + n3 * 0.18);
    float core = 1.0 - smoothstep(0.05, 1.05, length(centered));
    float glow = pow(max(core, 0.0), 1.9);

    vec3 color = mix(uColorA, uColorB, fluid);
    color = mix(color, uColorC, smoothstep(0.42, 0.9, n2));
    color += glow * uColorB * 0.32;

    float vignette = smoothstep(1.08, 0.12, length(centered));
    float alpha = (0.30 + 0.32 * fluid + 0.24 * glow) * vignette * uIntensity;

    gl_FragColor = vec4(color * alpha, alpha);
  }
`;

const PALETTES: Record<BackgroundPalette, [string, string, string]> = {
  "calm-blue": ["#0f2a44", "#38bdf8", "#14b8a6"],
  "warm-pink": ["#35142f", "#ec4899", "#fb923c"],
  "focus-cyan": ["#092b33", "#22d3ee", "#3b82f6"],
  "reflective-indigo": ["#171331", "#8b5cf6", "#38bdf8"],
  "calm-teal": ["#092b2c", "#14b8a6", "#38bdf8"],
  "muted-amber": ["#2b1d0b", "#f59e0b", "#ef4444"],
};

function color(hex: string) {
  return new THREE.Color(hex);
}

type Props = {
  palette: BackgroundPalette;
  intensity: BackgroundIntensity;
  motion: boolean;
};

export function CosmicFluidBackground({ palette, intensity, motion }: Props) {
  const mountRef = useRef<HTMLDivElement | null>(null);

  const colors = useMemo(() => PALETTES[palette] ?? PALETTES["calm-blue"], [palette]);
  const shaderIntensity = intensity === "medium" ? 0.88 : 0.56;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const shouldAnimate = motion && !reducedMotion;

    let frameId: number | null = null;
    let disposed = false;

    const scene = new THREE.Scene();
    const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);

    let renderer: THREE.WebGLRenderer;

    try {
      renderer = new THREE.WebGLRenderer({
        antialias: false,
        alpha: true,
        premultipliedAlpha: false,
        powerPreference: "low-power",
      });
    } catch {
      return;
    }

    mount.querySelectorAll("canvas").forEach((canvas) => canvas.remove());

    renderer.setClearColor(0x000000, 0);
    renderer.domElement.className = "cosmic-fluid-canvas";
    renderer.domElement.setAttribute("aria-hidden", "true");

    const pixelRatio = Math.min(
      Math.max(window.devicePixelRatio || 1, 1),
      intensity === "medium" ? 1.5 : 1.25,
    );

    renderer.setPixelRatio(pixelRatio);
    mount.appendChild(renderer.domElement);

    const uniforms = {
      uTime: { value: 0 },
      uResolution: { value: new THREE.Vector2(1, 1) },
      uColorA: { value: color(colors[0]) },
      uColorB: { value: color(colors[1]) },
      uColorC: { value: color(colors[2]) },
      uIntensity: { value: shaderIntensity },
    };

    const material = new THREE.ShaderMaterial({
      vertexShader,
      fragmentShader,
      uniforms,
      transparent: true,
      depthWrite: false,
      depthTest: false,
    });

    const geometry = new THREE.PlaneGeometry(2, 2);
    const mesh = new THREE.Mesh(geometry, material);
    scene.add(mesh);

    const resize = () => {
      if (disposed) return;
      const width = Math.max(mount.clientWidth || window.innerWidth, 1);
      const height = Math.max(mount.clientHeight || window.innerHeight, 1);
      renderer.setSize(width, height, false);
      uniforms.uResolution.value.set(width * pixelRatio, height * pixelRatio);
      renderer.render(scene, camera);
    };

    const tick = () => {
      if (disposed) return;

      if (!document.hidden) {
        uniforms.uTime.value += shouldAnimate ? 1.0 : 0.0;
        renderer.render(scene, camera);
      }

      if (shouldAnimate) {
        frameId = window.requestAnimationFrame(tick);
      }
    };

    const resizeObserver =
      typeof ResizeObserver !== "undefined" ? new ResizeObserver(resize) : null;

    resizeObserver?.observe(mount);
    window.addEventListener("resize", resize);
    document.addEventListener("visibilitychange", tick);

    resize();

    if (shouldAnimate) {
      frameId = window.requestAnimationFrame(tick);
    } else {
      renderer.render(scene, camera);
    }

    return () => {
      disposed = true;

      if (frameId !== null) {
        window.cancelAnimationFrame(frameId);
      }

      resizeObserver?.disconnect();
      window.removeEventListener("resize", resize);
      document.removeEventListener("visibilitychange", tick);

      scene.remove(mesh);
      geometry.dispose();
      material.dispose();

      mount.querySelectorAll("canvas").forEach((canvas) => canvas.remove());

      renderer.dispose();
      renderer.forceContextLoss();
    };
  }, [colors, intensity, motion, shaderIntensity]);

  return <div ref={mountRef} className="cosmic-fluid-mount" aria-hidden="true" />;
}
