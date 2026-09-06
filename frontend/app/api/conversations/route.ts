import { createClient } from "@/lib/supabase/server";

export const runtime = "edge";

const BACKEND_URL = process.env.FLY_BACKEND_URL!;

async function getAccessToken(): Promise<string | null> {
  const supabase = await createClient();

  const {
    data: { session },
  } = await supabase.auth.getSession();

  return session?.access_token ?? null;
}

function proxyResponse(upstream: Response): Response {
  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type":
        upstream.headers.get("Content-Type") || "application/json",
      "Cache-Control": "no-store",
    },
  });
}

export async function GET() {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return new Response("Unauthorized", { status: 401 });
  }

  const upstream = await fetch(
    `${BACKEND_URL}/conversations`,
    {
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      cache: "no-store",
    },
  );

  return proxyResponse(upstream);
}

export async function POST(req: Request) {
  const accessToken = await getAccessToken();

  if (!accessToken) {
    return new Response("Unauthorized", { status: 401 });
  }

  const body = await req.text();

  const upstream = await fetch(
    `${BACKEND_URL}/conversations`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      body,
      cache: "no-store",
    },
  );

  return proxyResponse(upstream);
}
