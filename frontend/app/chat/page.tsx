import { redirect } from "next/navigation";
import { createClient } from "@/lib/supabase/server";

export default async function ChatIndexPage() {
  const supabase = await createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) {
    redirect("/login");
  }

  const mainChat = await supabase
    .from("user_main_chats")
    .select("conversation_id")
    .eq("user_id", user.id)
    .maybeSingle();

  const mainChatId = mainChat.data?.conversation_id;

  if (mainChatId) {
    const conversation = await supabase
      .from("conversations")
      .select("id")
      .eq("id", mainChatId)
      .eq("user_id", user.id)
      .maybeSingle();

    if (conversation.data?.id) {
      redirect(`/chat/${conversation.data.id}`);
    }
  }

  const latestConversation = await supabase
    .from("conversations")
    .select("id")
    .eq("user_id", user.id)
    .order("updated_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (latestConversation.data?.id) {
    redirect(`/chat/${latestConversation.data.id}`);
  }

  redirect("/welcome");
}
