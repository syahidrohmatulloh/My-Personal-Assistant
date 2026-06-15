"use client";

import { useParams } from "next/navigation";
import { ChatV2Client } from "../chat-v2-client";

export default function ChatV2ConversationPage() {
  const params = useParams<{ id?: string | string[] }>();
  const rawId = params?.id;
  const conversationId = Array.isArray(rawId) ? rawId[0] : rawId;

  return <ChatV2Client conversationId={conversationId || null} />;
}
