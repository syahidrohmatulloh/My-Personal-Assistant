export const CHAT_V2_HANDOFF_STORAGE_KEY = "aliyya.chatV2.handoff.v1";

export type ChatV2HandoffMode = "life_companion" | "chief_of_staff";

export type ChatV2HandoffPayload = {
  source: "home" | "workspace" | string;
  text: string;
  createdAt: string;
  mode?: ChatV2HandoffMode;
  label?: string;
};

function compactHandoffText(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

export function saveChatV2Handoff(
  payload: Omit<ChatV2HandoffPayload, "createdAt">,
): boolean {
  if (typeof window === "undefined") return false;

  const text = compactHandoffText(payload.text);
  if (!text) return false;

  const next: ChatV2HandoffPayload = {
    ...payload,
    text,
    createdAt: new Date().toISOString(),
  };

  try {
    window.sessionStorage.setItem(CHAT_V2_HANDOFF_STORAGE_KEY, JSON.stringify(next));
    return true;
  } catch {
    return false;
  }
}

export function consumeChatV2Handoff(maxAgeMs = 15 * 60 * 1000): ChatV2HandoffPayload | null {
  if (typeof window === "undefined") return null;

  try {
    const raw = window.sessionStorage.getItem(CHAT_V2_HANDOFF_STORAGE_KEY);
    window.sessionStorage.removeItem(CHAT_V2_HANDOFF_STORAGE_KEY);

    if (!raw) return null;

    const parsed = JSON.parse(raw) as Partial<ChatV2HandoffPayload>;
    const text = compactHandoffText(parsed.text);
    if (!text) return null;

    const createdAt = typeof parsed.createdAt === "string" ? parsed.createdAt : "";
    const createdTime = createdAt ? new Date(createdAt).getTime() : 0;

    if (!createdTime || Number.isNaN(createdTime)) return null;
    if (Date.now() - createdTime > maxAgeMs) return null;

    return {
      source: typeof parsed.source === "string" ? parsed.source : "home",
      text,
      createdAt,
      mode:
        parsed.mode === "chief_of_staff" || parsed.mode === "life_companion"
          ? parsed.mode
          : undefined,
      label: typeof parsed.label === "string" ? parsed.label : undefined,
    };
  } catch {
    return null;
  }
}
