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

export async function createConversation(title = "New chat"): Promise<Conversation> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const r = await fetch(`${API_URL}/conversations`, {
    method: "POST",
    headers,
    body: JSON.stringify({ title }),
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

/**
 * Stream a chat response. Returns an async iterable of text deltas.
 *
 * Usage:
 *   for await (const delta of streamChat(convoId, "hello")) {
 *     setText(prev => prev + delta);
 *   }
 */
export async function* streamChat(
  conversationId: string,
  message: string,
): AsyncGenerator<string, void, unknown> {
  // Use the edge proxy at /api/chat instead of hitting Fly directly.
  // The proxy attaches the JWT server-side from cookies, so we don't need
  // to call getAuthHeader() here — saves a getSession() round-trip on every send.
  const response = await fetch(`/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_id: conversationId, message }),
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
      try {
        const parsed = JSON.parse(payload);
        if (parsed.type === "delta") yield parsed.text;
        else if (parsed.type === "error") throw new Error(parsed.message);
      } catch (err) {
        if (err instanceof SyntaxError) continue;
        throw err;
      }
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
