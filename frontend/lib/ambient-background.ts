export const BACKGROUND_STYLE_STORAGE_KEY = "assistant.background.style";
export const BACKGROUND_INTENSITY_STORAGE_KEY = "assistant.background.intensity";
export const BACKGROUND_MOTION_STORAGE_KEY = "assistant.background.motion";
export const BACKGROUND_SETTINGS_EVENT = "assistant-background-settings";

export const BACKGROUND_STYLES = [
  "off",
  "cosmic-plasma",
  "nebula-drift",
  "micro-particle-flow",
  "orbital-rings",
  "voice-wave",
] as const;

export type BackgroundStyle = (typeof BACKGROUND_STYLES)[number];
export type BackgroundIntensity = "low" | "medium";

export type BackgroundSettings = {
  style: BackgroundStyle;
  intensity: BackgroundIntensity;
  motion: boolean;
};

export const DEFAULT_BACKGROUND_SETTINGS: BackgroundSettings = {
  style: "nebula-drift",
  intensity: "low",
  motion: true,
};

export const BACKGROUND_STYLE_LABELS: Record<BackgroundStyle, string> = {
  off: "Off",
  "cosmic-plasma": "Cosmic Plasma",
  "nebula-drift": "Nebula Drift",
  "micro-particle-flow": "Micro Particle Flow",
  "orbital-rings": "Orbital Rings",
  "voice-wave": "Voice Wave",
};

export const BACKGROUND_STYLE_DESCRIPTIONS: Record<BackgroundStyle, string> = {
  off: "Disable the ambient layer entirely.",
  "cosmic-plasma": "A soft Opera Neon-inspired plasma aura.",
  "nebula-drift": "Slow atmospheric clouds with low-contrast color depth.",
  "micro-particle-flow": "A subtle dotted flow field behind the interface.",
  "orbital-rings": "Thin elliptical rings with very slow orbital motion.",
  "voice-wave": "A gentle Deepgram-inspired waveform glow.",
};

function coerceStyle(value: string | null): BackgroundStyle {
  return BACKGROUND_STYLES.includes(value as BackgroundStyle)
    ? (value as BackgroundStyle)
    : DEFAULT_BACKGROUND_SETTINGS.style;
}

function coerceIntensity(value: string | null): BackgroundIntensity {
  return value === "medium" || value === "low"
    ? value
    : DEFAULT_BACKGROUND_SETTINGS.intensity;
}

export function readBackgroundSettings(): BackgroundSettings {
  if (typeof window === "undefined") return DEFAULT_BACKGROUND_SETTINGS;

  return {
    style: coerceStyle(window.localStorage.getItem(BACKGROUND_STYLE_STORAGE_KEY)),
    intensity: coerceIntensity(
      window.localStorage.getItem(BACKGROUND_INTENSITY_STORAGE_KEY),
    ),
    motion:
      window.localStorage.getItem(BACKGROUND_MOTION_STORAGE_KEY) === null
        ? DEFAULT_BACKGROUND_SETTINGS.motion
        : window.localStorage.getItem(BACKGROUND_MOTION_STORAGE_KEY) !== "false",
  };
}

export function saveBackgroundSettings(settings: BackgroundSettings) {
  if (typeof window === "undefined") return;

  window.localStorage.setItem(BACKGROUND_STYLE_STORAGE_KEY, settings.style);
  window.localStorage.setItem(BACKGROUND_INTENSITY_STORAGE_KEY, settings.intensity);
  window.localStorage.setItem(
    BACKGROUND_MOTION_STORAGE_KEY,
    settings.motion ? "true" : "false",
  );

  window.dispatchEvent(
    new CustomEvent<BackgroundSettings>(BACKGROUND_SETTINGS_EVENT, {
      detail: settings,
    }),
  );
}
