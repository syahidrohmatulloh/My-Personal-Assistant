import { createClient } from "@/lib/supabase/client";
import { applyRemoteCompanionMoodState } from "@/lib/companion-mood";
import type { CompanionMoodStateApi } from "@/lib/api";

export async function subscribeCompanionMoodRealtime(conversationId: string) {
  const supabase = createClient();

  const {
    data: { user },
  } = await supabase.auth.getUser();

  if (!user) return () => {};

  const channel = supabase
    .channel(`companion-mood:${user.id}`)
    .on(
      "postgres_changes",
      {
        event: "*",
        schema: "public",
        table: "companion_mood_state",
        filter: `user_id=eq.${user.id}`,
      },
      (payload) => {
        const next = payload.new as CompanionMoodStateApi | null;
        if (!next) return;
        applyRemoteCompanionMoodState(next, conversationId);
      },
    )
    .subscribe();

  return () => {
    void supabase.removeChannel(channel);
  };
}
