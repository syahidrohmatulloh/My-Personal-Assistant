"use client";

import { useCallback, useEffect, useState } from "react";
import type { AssistantMode } from "@/lib/api";
import { cardsForMode } from "./cards";
import { modeKey, type WorkspaceCardId } from "./types";

const STORAGE_KEY = "aliyya.chatV2.workspace.v2";

export type WorkspaceModePreferences = {
  order: WorkspaceCardId[];
  hidden: WorkspaceCardId[];
};

export type WorkspacePreferences = {
  version: 2;
  life: WorkspaceModePreferences;
  chief: WorkspaceModePreferences;
};

function defaultModePreferences(mode: AssistantMode): WorkspaceModePreferences {
  const cards = cardsForMode(mode);
  return {
    order: cards.map((card) => card.id),
    hidden: cards.filter((card) => !card.defaultVisible).map((card) => card.id),
  };
}

export function defaultPreferences(): WorkspacePreferences {
  return {
    version: 2,
    life: defaultModePreferences("life_companion"),
    chief: defaultModePreferences("chief_of_staff"),
  };
}

function sanitizeModePreferences(
  raw: unknown,
  mode: AssistantMode,
): WorkspaceModePreferences {
  const defaults = defaultModePreferences(mode);
  const validIds = new Set<WorkspaceCardId>(defaults.order);

  const value = (raw && typeof raw === "object" ? raw : {}) as {
    order?: unknown;
    hidden?: unknown;
  };

  const storedOrder = Array.isArray(value.order)
    ? value.order.filter(
        (id): id is WorkspaceCardId =>
          typeof id === "string" && validIds.has(id as WorkspaceCardId),
      )
    : [];
  const order = storedOrder.filter((id, index) => storedOrder.indexOf(id) === index);

  // Cards the stored preferences have never seen (e.g. shipped after the
  // preferences were saved) are appended and respect their own default
  // visibility, so new cards never appear unannounced.
  const knownIds = new Set(order);
  const newIds = defaults.order.filter((id) => !knownIds.has(id));
  for (const id of newIds) order.push(id);

  const storedHidden = Array.isArray(value.hidden)
    ? value.hidden.filter(
        (id): id is WorkspaceCardId =>
          typeof id === "string" && validIds.has(id as WorkspaceCardId),
      )
    : defaults.hidden;
  const hidden = new Set(storedHidden);
  for (const id of newIds) {
    if (defaults.hidden.includes(id)) hidden.add(id);
  }

  return { order, hidden: Array.from(hidden) };
}

function readStoredPreferences(): WorkspacePreferences | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { life?: unknown; chief?: unknown };
    return {
      version: 2,
      life: sanitizeModePreferences(parsed?.life, "life_companion"),
      chief: sanitizeModePreferences(parsed?.chief, "chief_of_staff"),
    };
  } catch {
    return null;
  }
}

export function useWorkspacePreferences() {
  const [preferences, setPreferences] = useState<WorkspacePreferences>(defaultPreferences);

  useEffect(() => {
    const stored = readStoredPreferences();
    if (stored) setPreferences(stored);
  }, []);

  const persist = useCallback((next: WorkspacePreferences) => {
    setPreferences(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    } catch {}
  }, []);

  const toggleCard = useCallback(
    (mode: AssistantMode, cardId: WorkspaceCardId) => {
      const key = modeKey(mode);
      const current = preferences[key];
      const hidden = current.hidden.includes(cardId)
        ? current.hidden.filter((id) => id !== cardId)
        : [...current.hidden, cardId];
      persist({ ...preferences, [key]: { ...current, hidden } });
    },
    [preferences, persist],
  );

  const moveCard = useCallback(
    (mode: AssistantMode, cardId: WorkspaceCardId, direction: -1 | 1) => {
      const key = modeKey(mode);
      const current = preferences[key];
      const index = current.order.indexOf(cardId);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.order.length) return;
      const order = [...current.order];
      [order[index], order[target]] = [order[target], order[index]];
      persist({ ...preferences, [key]: { ...current, order } });
    },
    [preferences, persist],
  );

  const resetMode = useCallback(
    (mode: AssistantMode) => {
      const key = modeKey(mode);
      persist({
        ...preferences,
        [key]: defaultModePreferences(mode),
      });
    },
    [preferences, persist],
  );

  return { preferences, toggleCard, moveCard, resetMode };
}
