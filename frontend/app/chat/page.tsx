import { cookies } from "next/headers";
import { ChatHomePageClient } from "./page-client";

function decodeCookieValue(value: string | undefined): string {
  if (!value) return "";

  try {
    return decodeURIComponent(value).trim();
  } catch {
    return value.trim();
  }
}

export default async function ChatPage() {
  const cookieStore = await cookies();
  const initialAssistantName = decodeCookieValue(
    cookieStore.get("app-assistant-name")?.value,
  );

  return <ChatHomePageClient initialAssistantName={initialAssistantName} />;
}
