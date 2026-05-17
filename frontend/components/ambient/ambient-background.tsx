"use client";

import { useEffect, useMemo, useState } from "react";
import {
  BACKGROUND_MOOD_EVENT,
  BACKGROUND_SETTINGS_EVENT,
  type BackgroundMoodHint,
  type BackgroundSettings,
  DEFAULT_BACKGROUND_MOOD,
  DEFAULT_BACKGROUND_SETTINGS,
  readBackgroundMoodHint,
  readBackgroundSettings,
} from "@/lib/ambient-background";
import { cn } from "@/lib/utils";

export function AmbientBackground() {
  const [settings, setSettings] = useState<BackgroundSettings>(DEFAULT_BACKGROUND_SETTINGS);
  const [mood, setMood] = useState<BackgroundMoodHint>(DEFAULT_BACKGROUND_MOOD);

  useEffect(() => {
    function syncFromStorage() {
      setSettings(readBackgroundSettings());
      setMood(readBackgroundMoodHint());
    }

    function onSettingsEvent(event: Event) {
      const custom = event as CustomEvent<BackgroundSettings>;
      setSettings(custom.detail ?? readBackgroundSettings());
    }

    function onMoodEvent(event: Event) {
      const custom = event as CustomEvent<BackgroundMoodHint>;
      setMood(custom.detail ?? readBackgroundMoodHint());
    }

    syncFromStorage();
    window.addEventListener("storage", syncFromStorage);
    window.addEventListener(BACKGROUND_SETTINGS_EVENT, onSettingsEvent);
    window.addEventListener(BACKGROUND_MOOD_EVENT, onMoodEvent);
    return () => {
      window.removeEventListener("storage", syncFromStorage);
      window.removeEventListener(BACKGROUND_SETTINGS_EVENT, onSettingsEvent);
      window.removeEventListener(BACKGROUND_MOOD_EVENT, onMoodEvent);
    };
  }, []);

  const effectivePalette = useMemo(
    () => (settings.mode === "mood-based" ? mood.palette : null),
    [settings.mode, mood.palette],
  );

  if (settings.style === "off") return null;

  return (
    <div
      aria-hidden="true"
      data-background-style={settings.style}
      data-background-mode={settings.mode}
      data-background-mood={settings.mode === "mood-based" ? mood.mood : "manual"}
      className={cn(
        "ambient-background",
        `ambient-style-${settings.style}`,
        `ambient-intensity-${settings.intensity}`,
        effectivePalette && `ambient-palette-${effectivePalette}`,
        settings.mode === "mood-based" && "ambient-mood-based",
        !settings.motion && "ambient-static",
      )}
    >
      <span className="ambient-layer ambient-layer-a" />
      <span className="ambient-layer ambient-layer-b" />
      <span className="ambient-layer ambient-layer-c" />
      <span className="ambient-readability-vignette" />
    </div>
  );
}
