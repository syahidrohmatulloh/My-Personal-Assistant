"use client";

import { useEffect, useState } from "react";
import {
  BACKGROUND_SETTINGS_EVENT,
  type BackgroundSettings,
  readBackgroundSettings,
  DEFAULT_BACKGROUND_SETTINGS,
} from "@/lib/ambient-background";
import { cn } from "@/lib/utils";

export function AmbientBackground() {
  const [settings, setSettings] = useState<BackgroundSettings>(DEFAULT_BACKGROUND_SETTINGS);

  useEffect(() => {
    function syncFromStorage() {
      setSettings(readBackgroundSettings());
    }

    function onCustomEvent(event: Event) {
      const custom = event as CustomEvent<BackgroundSettings>;
      setSettings(custom.detail ?? readBackgroundSettings());
    }

    syncFromStorage();
    window.addEventListener("storage", syncFromStorage);
    window.addEventListener(BACKGROUND_SETTINGS_EVENT, onCustomEvent);
    return () => {
      window.removeEventListener("storage", syncFromStorage);
      window.removeEventListener(BACKGROUND_SETTINGS_EVENT, onCustomEvent);
    };
  }, []);

  if (settings.style === "off") return null;

  return (
    <div
      aria-hidden="true"
      className={cn(
        "ambient-background",
        `ambient-style-${settings.style}`,
        `ambient-intensity-${settings.intensity}`,
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
