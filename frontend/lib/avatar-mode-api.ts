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

export type AvatarAnimationStyle = "calm" | "subtle" | "minimal";

export type AvatarProfile = {
  id?: string | null;
  user_id?: string | null;
  image_url: string | null;
  avatar_mode_enabled: boolean;
  consent_confirmed: boolean;
  animation_style: AvatarAnimationStyle;
  created_at?: string | null;
  updated_at?: string | null;
};

export type AvatarProfilePatch = Partial<
  Pick<AvatarProfile, "image_url" | "avatar_mode_enabled" | "consent_confirmed" | "animation_style">
>;

export async function getAvatarProfile(): Promise<AvatarProfile> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/avatar-mode/profile`, { headers });
  if (!response.ok) throw new Error(`getAvatarProfile failed: ${response.status}`);
  return response.json();
}

export async function updateAvatarProfile(patch: AvatarProfilePatch): Promise<AvatarProfile> {
  const headers = { ...(await getAuthHeader()), "Content-Type": "application/json" };
  const response = await fetch(`${API_URL}/avatar-mode/profile`, {
    method: "PUT",
    headers,
    body: JSON.stringify(patch),
  });

  if (!response.ok) {
    let message = `updateAvatarProfile failed: ${response.status}`;
    try {
      const data = await response.json();
      if (data?.detail) message = data.detail;
    } catch {
      // Keep fallback message.
    }
    throw new Error(message);
  }

  return response.json();
}

export async function deleteAvatarProfile(): Promise<void> {
  const headers = await getAuthHeader();
  const response = await fetch(`${API_URL}/avatar-mode/profile`, {
    method: "DELETE",
    headers,
  });
  if (!response.ok && response.status !== 204) {
    throw new Error(`deleteAvatarProfile failed: ${response.status}`);
  }
}
