/**
 * Assistant-mode event plumbing for Chat V2.
 *
 * The app coordinates assistant-mode changes through a window CustomEvent.
 * Several surfaces dispatch it (settings save in lib/api.ts, the main chat's
 * stream meta, Chat V2 itself) and several listen (ambient background, the
 * main chat, Chat V2).
 *
 * Contract that keeps this safe:
 * - `broadcastAssistantMode` is called ONLY by the surface that initiates a
 *   mode change.
 * - Event listeners APPLY the incoming mode (state + storage) and never
 *   re-broadcast it. `window.dispatchEvent` is synchronous, so re-dispatching
 *   the event you are currently handling recurses into your own listener
 *   until the call stack overflows.
 */

export const ASSISTANT_MODE_EVENT = "assistant-companion-settings";

export type AssistantModeValue = "life_companion" | "chief_of_staff";

/**
 * Reads an assistant mode out of an event detail. Accepts both shapes used
 * across the app: `{ assistant_mode }` (chat surfaces) and full companion
 * settings objects, plus the legacy nested `{ preferences: { assistant_mode } }`.
 * Returns null for anything else.
 */
export function extractAssistantMode(detail: unknown): AssistantModeValue | null {
  const value = (detail && typeof detail === "object" ? detail : {}) as {
    assistant_mode?: unknown;
    preferences?: { assistant_mode?: unknown } | null;
  };
  const candidate = value.assistant_mode ?? value.preferences?.assistant_mode;
  return candidate === "chief_of_staff" || candidate === "life_companion"
    ? candidate
    : null;
}

export function createAssistantModeDetail(
  mode: AssistantModeValue,
): { assistant_mode: AssistantModeValue } {
  return { assistant_mode: mode };
}

/**
 * Reads an assistant name out of an event detail. The settings persistence
 * layer (lib/api.ts patchCompanionSettings) broadcasts the full companion
 * settings object on success, which carries `assistant_name`.
 */
export function extractAssistantName(detail: unknown): string | null {
  const value = (detail && typeof detail === "object" ? detail : {}) as {
    assistant_name?: unknown;
  };
  return typeof value.assistant_name === "string" && value.assistant_name.trim()
    ? value.assistant_name.trim()
    : null;
}

/**
 * Broadcasts a mode change to the rest of the app. Call this only from a
 * surface that initiates a change AND whose persistence path does not already
 * broadcast. Today the app has exactly two broadcasters: lib/api.ts
 * patchCompanionSettings (dispatches full settings on successful save) and
 * the chat stream sender (optimistic + server-confirmed mode commands).
 * Chat V2 itself therefore never calls this; it is kept as the canonical
 * dispatcher for any future surface that needs to self-broadcast. Never call
 * it from an ASSISTANT_MODE_EVENT listener.
 */
export function broadcastAssistantMode(mode: AssistantModeValue): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(ASSISTANT_MODE_EVENT, {
      detail: createAssistantModeDetail(mode),
    }),
  );
}

/** Injectable side effects for a user-initiated mode change. */
export type ModeChangeIO = {
  /** Update this surface only: React state + localStorage. Never dispatches. */
  applyLocally: (mode: AssistantModeValue) => void;
  /**
   * Persist to the backend (patchCompanionSettings). On success the API layer
   * broadcasts the global settings event — that is the single broadcaster for
   * this initiated change.
   */
  persist: (mode: AssistantModeValue) => Promise<unknown>;
  /** Fetch the server's current mode, used to resync after a failed persist. */
  fetchServerMode: () => Promise<AssistantModeValue>;
};

/**
 * Orchestrates a user-initiated assistant-mode change (e.g. the Chat V2
 * toggle). Contract:
 * - local state changes immediately;
 * - exactly one global broadcast per successful change, emitted by the
 *   persistence layer, not by this function;
 * - a failed persist resyncs local state to the server's mode WITHOUT
 *   broadcasting (other surfaces never heard about the failed change, so
 *   their state already matches the server);
 * - a failed resync fetch leaves the optimistic local state and never throws.
 */
export async function changeAssistantMode(
  mode: AssistantModeValue,
  io: ModeChangeIO,
): Promise<void> {
  io.applyLocally(mode);

  try {
    await io.persist(mode);
  } catch {
    try {
      io.applyLocally(await io.fetchServerMode());
    } catch {
      // Keep the optimistic local state; the next settings fetch reconciles.
    }
  }
}
