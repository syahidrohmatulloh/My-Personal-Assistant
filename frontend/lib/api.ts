import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

/**
 * Get the current JWT from Supabase. We attach it to every backend request.
 */
async function getAuthHeader(): Promise<HeadersInit> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${session.access_token}` };
}

export type Conversation = {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  style_profile_id?: string | null;
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
};

export type Memory = {
  id: string;
  content: string;
  kind: "fact" | "preference" | "context";
  source: "auto" | "manual";
  created_at: string;
};

export async function listMemories(): Promise<Memory[]> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/memories`, { headers });
  if (!r.ok) throw new Error(`listMemories failed: ${r.status}`);
  return r.json();
}

export async function createMemory(
  content: string,
  kind: Memory["kind"] = "fact",
): Promise<Memory> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/memories`, {
    method: "POST",
    headers,
    body: JSON.stringify({ content, kind }),
  });
  if (!r.ok) throw new Error(`createMemory failed: ${r.status}`);
  return r.json();
}

export async function deleteMemory(id: string): Promise<void> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/memories/${id}`, { method: "DELETE", headers });
  if (!r.ok && r.status !== 204) throw new Error(`deleteMemory failed: ${r.status}`);
}

export async function clearAllMemories(): Promise<void> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/memories`, { method: "DELETE", headers });
  if (!r.ok && r.status !== 204) throw new Error(`clearAllMemories failed: ${r.status}`);
}

export async function listConversations(): Promise<Conversation[]> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/conversations`, { headers });
  if (!r.ok) throw new Error(`listConversations failed: ${r.status}`);
  return r.json();
}

export async function createConversation(
  title = "New chat",
  styleProfileId?: string | null,
): Promise<Conversation> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const body: Record<string, unknown> = { title };
  if (styleProfileId) body.style_profile_id = styleProfileId;
  const r = await fetch(`${API_URL}/conversations`, {
    method: "POST",
    headers,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`createConversation failed: ${r.status}`);
  return r.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/conversations/${id}`, { method: "DELETE", headers });
  if (!r.ok && r.status !== 204) throw new Error(`deleteConversation failed: ${r.status}`);
}

export async function listMessages(conversationId: string): Promise<Message[]> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/conversations/${conversationId}/messages`, { headers });
  if (!r.ok) throw new Error(`listMessages failed: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Streaming chat — Phase 4.12 emits typing meta as the first SSE event.
// ---------------------------------------------------------------------------

/**
 * Companion mode names known to the backend (Phase 4.11).
 * Frontend treats anything outside this set as "unknown" and applies
 * heuristic pacing.
 */
export type CompanionMode =
  | "strategist"
  | "listener"
  | "motivator"
  | "challenger"
  | "reflective"
  | "practical"
  | "unknown";

/**
 * Pacing hint from backend. Frontend maps these to reveal-speed presets,
 * with `prefers-reduced-motion` forcing "immediate" regardless.
 */
export type Pacing = "immediate" | "fast" | "natural" | "slow";

export type ChatStreamEvent =
  | { type: "meta"; mode: CompanionMode; pacing: Pacing; assistantName: string }
  | { type: "delta"; text: string }
  | { type: "error"; message: string }
  | { type: "done" };

const VALID_MODES: ReadonlySet<string> = new Set<CompanionMode>([
  "strategist",
  "listener",
  "motivator",
  "challenger",
  "reflective",
  "practical",
  "unknown",
]);

const VALID_PACINGS: ReadonlySet<string> = new Set<Pacing>([
  "immediate",
  "fast",
  "natural",
  "slow",
]);

/**
 * Stream a chat response. Returns an async iterable of typed events.
 *
 * Backward compatibility:
 *   - If the backend doesn't emit `meta`, we never yield one — consumers
 *     should handle the absence.
 *   - If the backend emits an event with an unknown `type`, we skip it
 *     silently. Future backend additions won't break older frontends.
 *   - Malformed JSON lines are skipped (matches previous behaviour).
 *   - On `error`, we still throw — preserves previous try/catch semantics.
 *
 * Usage:
 *   for await (const evt of streamChat(convoId, "hello")) {
 *     if (evt.type === "delta") setText(prev => prev + evt.text);
 *     else if (evt.type === "meta") setPacing(evt.pacing);
 *   }
 */
export async function* streamChat(
  conversationId: string,
  message: string,
  attachmentIds: string[] = [],
): AsyncGenerator<ChatStreamEvent, void, unknown> {
  // Use the edge proxy at /api/chat instead of hitting Fly directly.
  // The proxy attaches the JWT server-side from cookies, so we don't need
  // to call getAuthHeader() here — saves a getSession() round-trip on every send.
  const response = await fetch(`/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      conversation_id: conversationId,
      message,
      attachment_ids: attachmentIds,
    }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`chat failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";

    for (const event of events) {
      const line = event.trim();
      if (!line.startsWith("data: ")) continue;

      const payload = line.slice(6);
      let parsed: unknown;
      try {
        parsed = JSON.parse(payload);
      } catch {
        // Malformed JSON line — skip silently (same as previous behaviour).
        continue;
      }

      if (!parsed || typeof parsed !== "object") continue;
      const obj = parsed as Record<string, unknown>;
      const type = obj.type;

      if (type === "delta" && typeof obj.text === "string") {
        yield { type: "delta", text: obj.text };
      } else if (type === "error" && typeof obj.message === "string") {
        // Surface as an event AND throw — keeps the previous throw semantics
        // so existing try/catch in the chat page still works.
        yield { type: "error", message: obj.message };
        throw new Error(obj.message);
      } else if (type === "done") {
        yield { type: "done" };
      } else if (type === "meta") {
        // Defensive narrowing — backend may evolve. We only forward the
        // event if mode & pacing land in our known sets, otherwise fall
        // through to a safe default the frontend treats as "use heuristic".
        const rawMode = typeof obj.mode === "string" ? obj.mode : "unknown";
        const rawPacing = typeof obj.pacing === "string" ? obj.pacing : "natural";
        const rawName =
          typeof obj.assistant_name === "string" && obj.assistant_name.trim()
            ? obj.assistant_name.trim()
            : "Assistant";

        const mode: CompanionMode = VALID_MODES.has(rawMode)
          ? (rawMode as CompanionMode)
          : "unknown";
        const pacing: Pacing = VALID_PACINGS.has(rawPacing)
          ? (rawPacing as Pacing)
          : "natural";

        yield { type: "meta", mode, pacing, assistantName: rawName };
      }
      // Unknown event types: ignore silently. Future-proof.
    }
  }
}

// ---------------------------------------------------------------------------
// Phase 3 — life model
// ---------------------------------------------------------------------------

export type Identity = {
  profile: Record<string, unknown>;
  narrative: string | null;
  updated_at: string | null;
};

export async function getIdentity(): Promise<Identity> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/identity`, { headers });
  if (!r.ok) throw new Error(`getIdentity failed: ${r.status}`);
  return r.json();
}

export async function putIdentity(
  profile: Record<string, unknown>,
  narrative?: string | null,
): Promise<Identity> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/identity`, {
    method: "PUT",
    headers,
    body: JSON.stringify({ profile, narrative }),
  });
  if (!r.ok) throw new Error(`putIdentity failed: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Phase 4 — journal
// ---------------------------------------------------------------------------

export type JournalEntry = {
  id: string;
  mood: number | null;
  energy: number | null;
  stress: number | null;
  note: string | null;
  observed_at: string;
};

export type JournalInput = {
  mood?: number | null;
  energy?: number | null;
  stress?: number | null;
  note?: string | null;
};

export async function getTodaysJournal(): Promise<{ entry: JournalEntry | null }> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/journal/today`, { headers });
  if (!r.ok) throw new Error(`getTodaysJournal failed: ${r.status}`);
  return r.json();
}

export async function postJournal(input: JournalInput): Promise<JournalEntry> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/journal`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`postJournal failed: ${r.status}`);
  return r.json();
}

export async function getRecentJournal(): Promise<JournalEntry[]> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/journal/recent`, { headers });
  if (!r.ok) throw new Error(`getRecentJournal failed: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Phase 3+ UI — goals, people, life events
// ---------------------------------------------------------------------------

export type Goal = {
  id: string;
  title: string;
  description: string | null;
  horizon: "week" | "month" | "quarter" | "year" | "multi_year" | "life";
  status: "active" | "paused" | "achieved" | "abandoned";
  emotional_weight: number;
  target_date: string | null;
  created_at: string;
  updated_at: string;
};

export type GoalInput = {
  title: string;
  description?: string | null;
  horizon: Goal["horizon"];
  emotional_weight?: number;
  target_date?: string | null;
};

export async function listGoals(status: Goal["status"] | "all" = "active"): Promise<Goal[]> {
  const headers = await getAuthHeader();
  const url =
    status === "all" ? `${API_URL}/goals?status=` : `${API_URL}/goals?status=${status}`;
  const r = await fetch(url, { headers });
  if (!r.ok) throw new Error(`listGoals failed: ${r.status}`);
  return r.json();
}

export async function createGoal(input: GoalInput): Promise<Goal> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/goals`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`createGoal failed: ${r.status}`);
  return r.json();
}

export async function updateGoalStatus(id: string, status: Goal["status"]): Promise<void> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/goals/${id}/status`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ status }),
  });
  if (!r.ok) throw new Error(`updateGoalStatus failed: ${r.status}`);
}

export async function deleteGoal(id: string): Promise<void> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/goals/${id}`, { method: "DELETE", headers });
  if (!r.ok && r.status !== 204) throw new Error(`deleteGoal failed: ${r.status}`);
}

export type Person = {
  id: string;
  name: string;
  relationship: string | null;
  importance: number;
  emotional_significance: number;
  birthday: string | null;
  details: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type PersonInput = {
  name: string;
  relationship?: string | null;
  importance?: number;
  emotional_significance?: number;
  birthday?: string | null;
  details?: Record<string, unknown>;
};

export async function listPeople(): Promise<Person[]> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/people`, { headers });
  if (!r.ok) throw new Error(`listPeople failed: ${r.status}`);
  return r.json();
}

export async function createPerson(input: PersonInput): Promise<Person> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/people`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
  if (!r.ok) throw new Error(`createPerson failed: ${r.status}`);
  return r.json();
}

export async function deletePerson(id: string): Promise<void> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/people/${id}`, { method: "DELETE", headers });
  if (!r.ok && r.status !== 204) throw new Error(`deletePerson failed: ${r.status}`);
}

// ---------------------------------------------------------------------------
// Daily briefing (Phase 4.7)
// ---------------------------------------------------------------------------

export type Briefing = {
  id: string;
  content: string;
  generated_at: string;
  conversation_id: string | null;
  opened_at: string | null;
};

function localDateYYYYMMDD(): string {
  // Browser's local "today" — sidesteps server-side timezone resolution.
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export async function getTodayBriefing(): Promise<Briefing | null> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/briefing/today?date=${localDateYYYYMMDD()}`, {
    headers,
  });
  if (!r.ok) throw new Error(`briefing failed: ${r.status}`);
  const data = await r.json();
  return (data?.briefing ?? null) as Briefing | null;
}

export async function openBriefing(
  briefingId: string,
  title?: string,
): Promise<{ conversation_id: string }> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/briefing/${briefingId}/open`, {
    method: "POST",
    headers,
    body: JSON.stringify({ title: title ?? null }),
  });
  if (!r.ok) throw new Error(`open briefing failed: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Conversation rename (Phase 4.8)
// ---------------------------------------------------------------------------

export async function renameConversation(
  id: string,
  title: string,
): Promise<Conversation> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/conversations/${id}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ title }),
  });
  if (!r.ok) throw new Error(`rename failed: ${r.status}`);
  return r.json();
}

export async function regenerateConversationTitle(id: string): Promise<Conversation> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/conversations/${id}/regenerate-title`, {
    method: "POST",
    headers,
  });
  if (!r.ok) throw new Error(`regenerate title failed: ${r.status}`);
  return r.json();
}

// ---------------------------------------------------------------------------
// Attachments (Phase 4.9 — vision + PDF upload)
// ---------------------------------------------------------------------------

export type AttachmentMeta = {
  id: string;
  kind: "image" | "document";
  media_type: string;
  original_filename: string;
  size_bytes: number;
};

/**
 * Resize image to max 1568px (long side) + JPEG 80% quality via Canvas API.
 * Returns a Blob. PDFs are passed through unchanged.
 *
 * Why this lives in lib/api.ts: the upload helper below needs to call it,
 * and we want a single place for "what gets sent to backend".
 */
async function maybeResize(file: File): Promise<Blob> {
  if (!file.type.startsWith("image/")) return file;
  // GIFs animate — resizing them loses animation. Skip.
  if (file.type === "image/gif") return file;

  const MAX_DIM = 1568;
  const QUALITY = 0.8;

  const bitmap = await createImageBitmap(file).catch(() => null);
  if (!bitmap) return file; // fallback: send original

  const { width, height } = bitmap;
  if (Math.max(width, height) <= MAX_DIM && file.size <= 1_000_000) {
    return file; // already small enough
  }

  const scale = Math.min(1, MAX_DIM / Math.max(width, height));
  const w = Math.round(width * scale);
  const h = Math.round(height * scale);

  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) return file;
  ctx.drawImage(bitmap, 0, 0, w, h);

  const blob: Blob | null = await new Promise((resolve) =>
    canvas.toBlob(resolve, "image/jpeg", QUALITY),
  );
  return blob ?? file;
}

export async function uploadAttachment(file: File): Promise<AttachmentMeta> {
  const blob = await maybeResize(file);
  const headers = await getAuthHeader();
  const form = new FormData();
  // For resized images, force .jpg extension on the filename.
  const filename =
    blob.type === "image/jpeg" && !file.name.toLowerCase().endsWith(".jpg") && !file.name.toLowerCase().endsWith(".jpeg")
      ? file.name.replace(/\.[^.]+$/, "") + ".jpg"
      : file.name;
  form.append("file", blob, filename);

  const r = await fetch(`${API_URL}/attachments/upload`, {
    method: "POST",
    headers, // do NOT set Content-Type — browser sets multipart boundary
    body: form,
  });
  if (!r.ok) {
    let detail = `upload failed: ${r.status}`;
    try {
      const j = await r.json();
      if (j?.detail) detail = j.detail;
    } catch {}
    throw new Error(detail);
  }
  return r.json();
}

// ---------------------------------------------------------------------------
// Style Profiles (Phase 4.11)
// ---------------------------------------------------------------------------

export type StyleProfile = {
  id: string;
  profile_name: string;
  source_type: "whatsapp" | "telegram" | "plain" | "pasted";
  extracted_style: Record<string, unknown>;
  sample_count: number;
  confidence: number | null;
  created_at: string;
  updated_at: string;
};

export type AnalyzeResult = {
  profile: Record<string, unknown>;
  sample_count: number;
  source_type: string;
  suggested_name: string;
  warnings: string[];
};

export type PreviewSender = {
  name: string;
  count: number;
  is_likely_user: boolean;
  recommended: boolean;
};

export type PreviewParseResult = {
  source_type: string;
  message_count: number;
  senders: PreviewSender[];
  recommended_target_name: string | null;
  too_long: boolean;
  warnings: string[];
};

export async function previewParseStyle(
  transcript: string,
): Promise<PreviewParseResult> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/style-profiles/preview-parse`, {
    method: "POST",
    headers,
    body: JSON.stringify({ transcript }),
  });
  if (!r.ok) {
    let detail = `preview parse failed: ${r.status}`;
    try { const j = await r.json(); if (j?.detail) detail = j.detail; } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export async function analyzeStyle(
  transcript: string,
  targetName?: string,
): Promise<AnalyzeResult> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/style-profiles/analyze`, {
    method: "POST",
    headers,
    body: JSON.stringify({ transcript, target_name: targetName || null }),
  });
  if (!r.ok) {
    let detail = `analyze failed: ${r.status}`;
    try { const j = await r.json(); if (j?.detail) detail = j.detail; } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export async function listStyleProfiles(): Promise<StyleProfile[]> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/style-profiles`, { headers });
  if (!r.ok) throw new Error(`list profiles failed: ${r.status}`);
  return r.json();
}

export async function createStyleProfile(input: {
  profile_name: string;
  source_type: string;
  extracted_style: Record<string, unknown>;
  sample_count: number;
}): Promise<StyleProfile> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/style-profiles`, {
    method: "POST",
    headers,
    body: JSON.stringify(input),
  });
  if (!r.ok) {
    let detail = `create profile failed: ${r.status}`;
    try { const j = await r.json(); if (j?.detail) detail = j.detail; } catch {}
    throw new Error(detail);
  }
  return r.json();
}

export async function renameStyleProfile(id: string, name: string): Promise<StyleProfile> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/style-profiles/${id}`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ profile_name: name }),
  });
  if (!r.ok) throw new Error(`rename failed: ${r.status}`);
  return r.json();
}

export async function deleteStyleProfile(id: string): Promise<void> {
  const headers = await getAuthHeader();
  const r = await fetch(`${API_URL}/style-profiles/${id}`, { method: "DELETE", headers });
  if (!r.ok && r.status !== 204) throw new Error(`delete failed: ${r.status}`);
}

// ---------------------------------------------------------------------------
// Conversation style assignment
// ---------------------------------------------------------------------------

export async function setConversationStyle(
  conversationId: string,
  styleProfileId: string | null,
): Promise<Conversation> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/conversations/${conversationId}/style`, {
    method: "PATCH",
    headers,
    body: JSON.stringify({ style_profile_id: styleProfileId }),
  });
  if (!r.ok) {
    let detail = `set style failed: ${r.status}`;
    try { const j = await r.json(); if (j?.detail) detail = j.detail; } catch {}
    throw new Error(detail);
  }
  return r.json();
}
