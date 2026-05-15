import { createClient } from "@/lib/supabase/server";
import { redirect } from "next/navigation";
import { ChatShell } from "./chat-shell";
import type { Conversation } from "@/lib/api";

export default async function ChatLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const supabase = await createClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();
  if (!user) redirect("/login");

  const startOfDay = new Date();
  startOfDay.setHours(0, 0, 0, 0);

  const [convos, journal] = await Promise.all([
    supabase
      .from("conversations")
      .select("id, title, created_at, updated_at")
      .eq("user_id", user.id)
      .order("updated_at", { ascending: false })
      .limit(50),
    supabase
      .from("emotional_state")
      .select("id")
      .eq("user_id", user.id)
      .eq("source", "self_report")
      .eq("superseded", false)
      .gte("observed_at", startOfDay.toISOString())
      .limit(1)
      .maybeSingle(),
  ]);

  return (
    <ChatShell
      initialConversations={(convos.data ?? []) as Conversation[]}
      initialJournaled={!!journal.data}
    >
      {children}
    </ChatShell>
  );
}
