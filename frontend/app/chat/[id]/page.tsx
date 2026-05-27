import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Message } from "@/lib/api";
import { ConversationPageClient } from "./conversation-page-client";

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
    .select("id, title")
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
    .order("created_at", { ascending: true });

  const initialIsMainChat = String(conversation.data.title || "").startsWith("Main Chat -");

  return (
    <ConversationPageClient
      conversationId={id}
      initialMessages={(messages.data ?? []) as Message[]}
      initialIsMainChat={initialIsMainChat}
    />
  );
}
