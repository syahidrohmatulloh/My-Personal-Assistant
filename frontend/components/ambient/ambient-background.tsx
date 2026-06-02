"use client";

import { useEffect, useMemo, useState } from "react";
import { getCompanionSettings, type AssistantMode } from "@/lib/api";
import {
  BACKGROUND_MOOD_EVENT,
  BACKGROUND_SETTINGS_EVENT,
  type BackgroundMoodHint,
  type BackgroundPalette,
  type BackgroundSettings,
  DEFAULT_BACKGROUND_MOOD,
  DEFAULT_BACKGROUND_SETTINGS,
  readBackgroundMoodHint,
  readBackgroundSettings,
} from "@/lib/ambient-background";
import { cn } from "@/lib/utils";
import { CosmicFluidBackground } from "./cosmic-fluid-background";
import { ChiefOfStaffOrbBackground } from "./chief-of-staff-orb-background";

export function AmbientBackground() {
  const [settings, setSettings] = useState<BackgroundSettings>(DEFAULT_BACKGROUND_SETTINGS);
  const [mood, setMood] = useState<BackgroundMoodHint>(DEFAULT_BACKGROUND_MOOD);
  const [assistantMode, setAssistantMode] = useState<AssistantMode>("life_companion");

  useEffect(() => {
    let cancelled = false;

    function syncFromStorage() {
      setSettings(readBackgroundSettings());
      setMood(readBackgroundMoodHint());
    }

    async function syncAssistantMode() {
      try {
        const settings = await getCompanionSettings();
        if (cancelled) return;
        setAssistantMode(
          settings.assistant_mode === "chief_of_staff"
            ? "chief_of_staff"
            : "life_companion",
        );
      } catch {
        if (!cancelled) {
          setAssistantMode("life_companion");
        }
      }
    }

    function onAssistantModeEvent(event: Event) {
      const detail = (event as CustomEvent<{ assistant_mode?: unknown; preferences?: { assistant_mode?: unknown } }>).detail;
      const eventMode = detail?.assistant_mode ?? detail?.preferences?.assistant_mode;

      if (eventMode === "chief_of_staff" || eventMode === "life_companion") {
        setAssistantMode(eventMode);
        return;
      }

      void syncAssistantMode();
    }

    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        void syncAssistantMode();
      }
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
    void syncAssistantMode();

    window.addEventListener("storage", syncFromStorage);
    window.addEventListener(BACKGROUND_SETTINGS_EVENT, onSettingsEvent);
    window.addEventListener(BACKGROUND_MOOD_EVENT, onMoodEvent);
    window.addEventListener("assistant-companion-settings", onAssistantModeEvent);
    window.addEventListener("focus", onAssistantModeEvent);
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      cancelled = true;
      window.removeEventListener("storage", syncFromStorage);
      window.removeEventListener(BACKGROUND_SETTINGS_EVENT, onSettingsEvent);
      window.removeEventListener(BACKGROUND_MOOD_EVENT, onMoodEvent);
      window.removeEventListener("assistant-companion-settings", onAssistantModeEvent);
      window.removeEventListener("focus", onAssistantModeEvent);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, []);

  const effectivePalette = useMemo(
    () => (settings.mode === "mood-based" ? mood.palette : null),
    [settings.mode, mood.palette],
  );
  const useFluidEffect = settings.effect === "fluid-webgl";
  const webglPalette = (effectivePalette ?? "calm-blue") as BackgroundPalette;

  if (assistantMode === "chief_of_staff") {
    return <ChiefOfStaffOrbBackground />;
  }

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

      {useFluidEffect && (
        <CosmicFluidBackground
          key={`${settings.style}-${settings.effect}-${webglPalette}-${settings.intensity}-${settings.motion ? "motion" : "static"}`}
          palette={webglPalette}
          intensity={settings.intensity}
          motion={settings.motion}
        />
      )}

      <span className="ambient-readability-vignette" />
    </div>
  );
}
