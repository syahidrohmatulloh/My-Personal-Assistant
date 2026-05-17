export const BACKGROUND_STYLE_STORAGE_KEY = "assistant.background.style";
export const BACKGROUND_INTENSITY_STORAGE_KEY = "assistant.background.intensity";
export const BACKGROUND_MOTION_STORAGE_KEY = "assistant.background.motion";
export const BACKGROUND_EFFECT_STORAGE_KEY = "assistant.background.effect";
export const BACKGROUND_MODE_STORAGE_KEY = "assistant.background.mode";
export const BACKGROUND_MOOD_STORAGE_KEY = "assistant.background.mood";
export const BACKGROUND_PALETTE_STORAGE_KEY = "assistant.background.palette";
export const BACKGROUND_SETTINGS_EVENT = "assistant-background-settings";
export const BACKGROUND_MOOD_EVENT = "assistant-background-mood";

export const BACKGROUND_STYLES = [
  "off",
  "cosmic-plasma",
  "nebula-drift",
  "micro-particle-flow",
  "orbital-rings",
  "voice-wave",
] as const;

export const BACKGROUND_PALETTES = [
  "calm-blue",
  "warm-pink",
  "focus-cyan",
  "reflective-indigo",
  "calm-teal",
  "muted-amber",
] as const;

export type BackgroundStyle = (typeof BACKGROUND_STYLES)[number];
export type BackgroundIntensity = "low" | "medium";
export type BackgroundMode = "manual" | "mood-based";
export type BackgroundEffect = "standard" | "fluid-webgl";
export type BackgroundPalette = (typeof BACKGROUND_PALETTES)[number];

export type BackgroundSettings = {
  style: BackgroundStyle;
  intensity: BackgroundIntensity;
  motion: boolean;
  mode: BackgroundMode;
  effect: BackgroundEffect;
};

export type BackgroundMoodHint = {
  mood: string;
  palette: BackgroundPalette;
};

export const DEFAULT_BACKGROUND_SETTINGS: BackgroundSettings = {
  style: "nebula-drift",
  effect: "standard",
  intensity: "low",
  motion: true,
  mode: "manual",
};

export const DEFAULT_BACKGROUND_MOOD: BackgroundMoodHint = {
  mood: "calm",
  palette: "calm-blue",
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

export const BACKGROUND_MODE_LABELS: Record<BackgroundMode, string> = {
  manual: "Manual",
  "mood-based": "Mood-based",
};

export const BACKGROUND_MODE_DESCRIPTIONS: Record<BackgroundMode, string> = {
  manual: "Keep the selected palette stable.",
  "mood-based": "Let chat mode subtly shift the ambient color palette.",
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

function coerceMode(value: string | null): BackgroundMode {
  return value === "mood-based" || value === "manual"
    ? value
    : DEFAULT_BACKGROUND_SETTINGS.mode;
}

function coercePalette(value: string | null): BackgroundPalette {
  return BACKGROUND_PALETTES.includes(value as BackgroundPalette)
    ? (value as BackgroundPalette)
    : DEFAULT_BACKGROUND_MOOD.palette;
}



export function readBackgroundEffect(): BackgroundEffect {
  if (typeof window === "undefined") return "standard";
  const raw = window.localStorage.getItem(BACKGROUND_EFFECT_STORAGE_KEY);
  return raw === "fluid-webgl" ? "fluid-webgl" : "standard";
}

export function saveBackgroundEffect(effect: BackgroundEffect) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(BACKGROUND_EFFECT_STORAGE_KEY, effect);
}

export function readBackgroundSettings(): BackgroundSettings {
  if (typeof window === "undefined") return DEFAULT_BACKGROUND_SETTINGS;

  return {
    style: coerceStyle(window.localStorage.getItem(BACKGROUND_STYLE_STORAGE_KEY)),
    effect: readBackgroundEffect(),
    intensity: coerceIntensity(
      window.localStorage.getItem(BACKGROUND_INTENSITY_STORAGE_KEY),
    ),
    motion:
      window.localStorage.getItem(BACKGROUND_MOTION_STORAGE_KEY) === null
        ? DEFAULT_BACKGROUND_SETTINGS.motion
        : window.localStorage.getItem(BACKGROUND_MOTION_STORAGE_KEY) !== "false",
    mode: coerceMode(window.localStorage.getItem(BACKGROUND_MODE_STORAGE_KEY)),
  };
}

export function readBackgroundMoodHint(): BackgroundMoodHint {
  if (typeof window === "undefined") return DEFAULT_BACKGROUND_MOOD;

  return {
    mood: window.sessionStorage.getItem(BACKGROUND_MOOD_STORAGE_KEY) || DEFAULT_BACKGROUND_MOOD.mood,
    palette: coercePalette(window.sessionStorage.getItem(BACKGROUND_PALETTE_STORAGE_KEY)),
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
  window.localStorage.setItem(BACKGROUND_MODE_STORAGE_KEY, settings.mode);

  window.dispatchEvent(
    new CustomEvent<BackgroundSettings>(BACKGROUND_SETTINGS_EVENT, {
      detail: settings,
    }),
  );
}

export function setBackgroundMoodHint(hint: Partial<BackgroundMoodHint>) {
  if (typeof window === "undefined") return;
  const current = readBackgroundMoodHint();
  const next: BackgroundMoodHint = {
    mood: hint.mood || current.mood,
    palette: coercePalette(hint.palette || current.palette),
  };
  window.sessionStorage.setItem(BACKGROUND_MOOD_STORAGE_KEY, next.mood);
  window.sessionStorage.setItem(BACKGROUND_PALETTE_STORAGE_KEY, next.palette);
  window.dispatchEvent(new CustomEvent<BackgroundMoodHint>(BACKGROUND_MOOD_EVENT, { detail: next }));
}

export function getLocalIsoWithOffset(date = new Date()) {
  const pad = (n: number) => String(Math.trunc(Math.abs(n))).padStart(2, "0");
  const offsetMinutes = -date.getTimezoneOffset();
  const sign = offsetMinutes >= 0 ? "+" : "-";
  const hours = pad(offsetMinutes / 60);
  const minutes = pad(offsetMinutes % 60);
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}${sign}${hours}:${minutes}`;
}

export function buildUiContextSnapshot() {
  const settings = readBackgroundSettings();
  const mood = readBackgroundMoodHint();
  const timezone =
    typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : undefined;
  const theme =
    typeof window !== "undefined" && window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";

  return {
    background_style: settings.style,
    background_intensity: settings.intensity,
    background_motion: settings.motion ? "animated" : "static",
    background_mode: settings.mode,
    background_palette_hint: mood.palette,
    mood_hint: mood.mood,
    theme,
    timezone,
    local_time_iso: getLocalIsoWithOffset(),
    client_platform: "web",
    current_page: "chat",
  };
}
