import { createClient } from "@/lib/supabase/client";

const API_URL = process.env.NEXT_PUBLIC_API_URL!;

async function getAuthHeader(): Promise<Record<string, string>> {
  const supabase = createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) throw new Error("Not authenticated");
  return { Authorization: `Bearer ${session.access_token}` };
}

export async function speakText(text: string): Promise<Response> {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("Text is required");

  const headers = {
    ...(await getAuthHeader()),
    "Content-Type": "application/json",
  };

  const response = await fetch(`${API_URL}/voice/speak`, {
    method: "POST",
    headers,
    body: JSON.stringify({ text: trimmed }),
  });

  if (!response.ok) {
    let message = `Speech generation failed: ${response.status}`;
    try {
      const data = await response.json();
      if (data?.detail) message = data.detail;
    } catch {
      // Keep fallback message.
    }
    throw new Error(message);
  }

  return response;
}
