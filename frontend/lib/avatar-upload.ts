import { createClient } from "@/lib/supabase/client";

export const ASSISTANT_AVATAR_BUCKET = "assistant-avatars";

const MAX_AVATAR_FILE_SIZE_BYTES = 5 * 1024 * 1024;

const ALLOWED_AVATAR_MIME_TYPES = new Set(["image/jpeg", "image/png", "image/webp"]);

function extensionForFile(file: File): string {
  if (file.type === "image/jpeg") return "jpg";
  if (file.type === "image/png") return "png";
  if (file.type === "image/webp") return "webp";

  const extension = file.name.split(".").pop()?.toLowerCase();
  if (extension === "jpg" || extension === "jpeg") return "jpg";
  if (extension === "png") return "png";
  if (extension === "webp") return "webp";

  return "png";
}

export function validateAssistantAvatarFile(file: File): void {
  if (!ALLOWED_AVATAR_MIME_TYPES.has(file.type)) {
    throw new Error("Please upload a JPG, PNG, or WebP image.");
  }

  if (file.size > MAX_AVATAR_FILE_SIZE_BYTES) {
    throw new Error("Avatar image must be 5 MB or smaller.");
  }
}

export async function uploadAssistantAvatarImage(file: File): Promise<string> {
  validateAssistantAvatarFile(file);

  const supabase = createClient();
  const {
    data: { user },
    error: userError,
  } = await supabase.auth.getUser();

  if (userError || !user) {
    throw new Error("Not authenticated");
  }

  const extension = extensionForFile(file);
  const fileName =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}-${Math.random().toString(36).slice(2)}`;

  const path = `${user.id}/${fileName}.${extension}`;

  const { error: uploadError } = await supabase.storage
    .from(ASSISTANT_AVATAR_BUCKET)
    .upload(path, file, {
      cacheControl: "3600",
      contentType: file.type,
      upsert: false,
    });

  if (uploadError) {
    throw new Error(uploadError.message || "Failed to upload avatar image.");
  }

  const { data } = supabase.storage.from(ASSISTANT_AVATAR_BUCKET).getPublicUrl(path);

  if (!data.publicUrl) {
    throw new Error("Failed to create avatar image URL.");
  }

  return data.publicUrl;
}
