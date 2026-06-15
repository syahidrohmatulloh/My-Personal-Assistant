"use client";

import { useCallback, useEffect, useState } from "react";
import { getCompanionSettings, type CompanionSettings } from "@/lib/api";

const FALLBACK_ASSISTANT_NAME = "Assistant";
const ASSISTANT_NAME_CACHE_KEY = "app:assistant-name";
const COMPANION_SETTINGS_EVENT = "assistant-companion-settings";

function cleanAssistantName(value: unknown): string | null {
  if (typeof value !== "string") return null;
  const cleaned = value.trim();
  return cleaned.length > 0 ? cleaned : null;
}

function readCachedAssistantName(): string | null {
  if (typeof window === "undefined") return null;

  try {
    return cleanAssistantName(window.localStorage.getItem(ASSISTANT_NAME_CACHE_KEY));
  } catch {
    return null;
  }
}

function writeCachedAssistantName(value: string): void {
  if (typeof window === "undefined") return;

  try {
    window.localStorage.setItem(ASSISTANT_NAME_CACHE_KEY, value);
  } catch {}
}

function pickAssistantNameFromSettings(value: unknown): string | null {
  const settings = value as Partial<CompanionSettings> | null | undefined;
  return cleanAssistantName(settings?.assistant_name);
}

export function getAssistantDisplayNameFromBrowser(): string {
  return readCachedAssistantName() || FALLBACK_ASSISTANT_NAME;
}

export function useAssistantDisplayName(fallback = FALLBACK_ASSISTANT_NAME): string {
  const [assistantName, setAssistantName] = useState<string>(() => readCachedAssistantName() || "");
  const [loaded, setLoaded] = useState<boolean>(() => Boolean(readCachedAssistantName()));

  const applyName = useCallback((value: unknown): boolean => {
    const nextName = cleanAssistantName(value);
    if (!nextName) return false;

    setAssistantName(nextName);
    writeCachedAssistantName(nextName);
    return true;
  }, []);

  const refreshFromSettings = useCallback(async () => {
    try {
      const settings = await getCompanionSettings();
      const nextName = pickAssistantNameFromSettings(settings);

      if (nextName) {
        applyName(nextName);
      } else {
        setAssistantName("");
      }
    } catch {
      const cached = readCachedAssistantName();
      if (cached) setAssistantName(cached);
    } finally {
      setLoaded(true);
    }
  }, [applyName]);

  useEffect(() => {
    let mounted = true;

    async function load() {
      try {
        const settings = await getCompanionSettings();
        if (!mounted) return;

        const nextName = pickAssistantNameFromSettings(settings);
        if (nextName) {
          applyName(nextName);
        } else {
          setAssistantName("");
        }
      } catch {
        if (!mounted) return;

        const cached = readCachedAssistantName();
        if (cached) setAssistantName(cached);
      } finally {
        if (mounted) setLoaded(true);
      }
    }

    void load();

    function onCompanionSettings(event: Event) {
      const detail = (event as CustomEvent<unknown>).detail;
      const nextName = pickAssistantNameFromSettings(detail);
      if (nextName) applyName(nextName);
    }

    function onFocus() {
      void refreshFromSettings();
    }

    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        void refreshFromSettings();
      }
    }

    window.addEventListener(COMPANION_SETTINGS_EVENT, onCompanionSettings);
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      mounted = false;
      window.removeEventListener(COMPANION_SETTINGS_EVENT, onCompanionSettings);
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [applyName, refreshFromSettings]);

  if (assistantName) return assistantName;
  if (!loaded) return "";

  return fallback;
}
