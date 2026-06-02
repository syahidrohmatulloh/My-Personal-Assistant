import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
import type { Message } from "@/lib/api";
import { ChatV2Client } from "./chat-v2-client";

const INITIAL_MESSAGE_LIMIT = 80;

export default async function ChatV2Page() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const conversations = await supabase
    .from("conversations")
    .select("id, title, updated_at")
    .eq("user_id", user.id)
    .order("updated_at", { ascending: false })
    .limit(50);

  const rows = conversations.data ?? [];
  const selectedConversation =
    rows.find((conversation) =>
      String(conversation.title || "").startsWith("Main Chat -"),
    ) ??
    rows[0] ??
    null;

  let initialMessages: Message[] = [];

  if (selectedConversation?.id) {
    const messages = await supabase
      .from("messages")
      .select("id, role, content, created_at")
      .eq("conversation_id", selectedConversation.id)
      .order("created_at", { ascending: false })
      .limit(INITIAL_MESSAGE_LIMIT);

    initialMessages = ((messages.data ?? []) as Message[]).slice().reverse();
  }

  return (
    <ChatV2Client
      initialMessages={initialMessages}
      conversationTitle={
        typeof selectedConversation?.title === "string"
          ? selectedConversation.title
          : null
      }
    />
  );
}
