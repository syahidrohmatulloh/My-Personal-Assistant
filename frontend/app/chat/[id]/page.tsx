import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";
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
    .select("id")
    .eq("id", id)
    .eq("user_id", user.id)
    .maybeSingle();

  if (!conversation.data?.id) {
    redirect("/chat");
  }

  // Cache-first chat UX:
  // Do not block the route render by fetching the full message history here.
  // ConversationPageClient reads the localStorage snapshot immediately, then
  // refreshes the latest messages in the background.
  return <ConversationPageClient conversationId={id} />;
}
