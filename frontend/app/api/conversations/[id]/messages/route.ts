import { createClient } from "@/lib/supabase/server";

export const runtime = "edge";

const BACKEND_URL = process.env.FLY_BACKEND_URL!;

export async function GET(
  req: Request,
  context: { params: Promise<{ id: string }> },
) {
  const { id } = await context.params;

  const supabase = await createClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();

  if (!session) {
    return new Response("Unauthorized", { status: 401 });
  }

  const requestUrl = new URL(req.url);
  const upstreamUrl = new URL(`${BACKEND_URL}/conversations/${id}/messages`);

  requestUrl.searchParams.forEach((value, key) => {
    if (key !== "_ts") {
      upstreamUrl.searchParams.set(key, value);
    }
  });

  const upstream = await fetch(upstreamUrl.toString(), {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
    },
    cache: "no-store",
  });

  return new Response(upstream.body, {
    status: upstream.status,
    headers: {
      "Content-Type": upstream.headers.get("Content-Type") || "application/json",
      "Cache-Control": "no-store",
    },
  });
}
