import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Message } from "@/lib/api";
import { ConversationPageClient } from "./conversation-page-client";

const INITIAL_MESSAGE_LIMIT = 80;

export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const conversation = await supabase
    .from("conversations")
    .select("id, title, style_profile_id")
    .eq("id", id)
    .eq("user_id", user.id)
    .maybeSingle();

  if (!conversation.data?.id) {
    redirect("/chat");
  }

  const messages = await supabase
    .from("messages")
    .select("id, role, content, created_at")
    .eq("conversation_id", id)
    .order("created_at", { ascending: false })
    .limit(INITIAL_MESSAGE_LIMIT);

  const initialMessages = ((messages.data ?? []) as Message[]).slice().reverse();
  const initialHasMoreMessages = (messages.data ?? []).length >= INITIAL_MESSAGE_LIMIT;

  const initialIsMainChat = String(conversation.data.title || "").startsWith("Main Chat -");
  const initialStyleProfileId =
    typeof conversation.data.style_profile_id === "string"
      ? conversation.data.style_profile_id
      : null;

  let initialStyleProfileName: string | null = null;

  if (initialStyleProfileId) {
    const styleProfile = await supabase
      .from("style_profiles")
      .select("profile_name")
      .eq("id", initialStyleProfileId)
      .eq("user_id", user.id)
      .maybeSingle();

    initialStyleProfileName =
      typeof styleProfile.data?.profile_name === "string"
        ? styleProfile.data.profile_name
        : null;
  }

  return (
    <ConversationPageClient
      conversationId={id}
      initialMessages={initialMessages}
      initialHasMoreMessages={initialHasMoreMessages}
      initialIsMainChat={initialIsMainChat}
      initialStyleProfileId={initialStyleProfileId}
      initialStyleProfileName={initialStyleProfileName}
    />
  );
}
