import { NextRequest, NextResponse } from "next/server"
import { createClient } from "@/lib/supabase/server"

const BACKEND_URL =
  process.env.FLY_BACKEND_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8080"

type RouteContext = {
  params: Promise<{ path?: string[] }>
}

async function proxyCalendar(
  req: NextRequest,
  context: RouteContext,
  method: "GET" | "POST",
) {
  const supabase = await createClient()
  const {
    data: { session },
  } = await supabase.auth.getSession()

  if (!session?.access_token) {
    return NextResponse.json({ detail: "Unauthorized" }, { status: 401 })
  }

  const { path = [] } = await context.params
  const suffix = path.length ? `/${path.map(encodeURIComponent).join("/")}` : ""
  const incomingUrl = new URL(req.url)
  const targetUrl = `${BACKEND_URL}/calendar${suffix}${incomingUrl.search}`

  const headers: Record<string, string> = {
    Authorization: `Bearer ${session.access_token}`,
  }

  let body: string | undefined
  if (method !== "GET") {
    body = await req.text()
    headers["Content-Type"] = req.headers.get("content-type") || "application/json"
  }

  const upstream = await fetch(targetUrl, {
    method,
    headers,
    body,
    cache: "no-store",
  })

  const text = await upstream.text()
  const contentType = upstream.headers.get("content-type") || "application/json"

  return new NextResponse(text, {
    status: upstream.status,
    headers: {
      "content-type": contentType,
    },
  })
}

export async function GET(req: NextRequest, context: RouteContext) {
  return proxyCalendar(req, context, "GET")
}

export async function POST(req: NextRequest, context: RouteContext) {
  return proxyCalendar(req, context, "POST")
}
