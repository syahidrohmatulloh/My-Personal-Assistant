import { NextRequest } from "next/server"

const BACKEND_URL =
  process.env.BACKEND_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "http://localhost:8000"

async function proxy(req: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  const { path = [] } = await context.params
  const incomingUrl = new URL(req.url)
  const suffix = path.length ? `/${path.join("/")}` : ""
  const targetUrl = `${BACKEND_URL}/calendar${suffix}${incomingUrl.search}`

  const headers = new Headers(req.headers)
  headers.delete("host")

  const body =
    req.method === "GET" || req.method === "HEAD" ? undefined : await req.arrayBuffer()

  return fetch(targetUrl, {
    method: req.method,
    headers,
    body,
    redirect: "manual",
  })
}

export async function GET(req: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return proxy(req, context)
}

export async function POST(req: NextRequest, context: { params: Promise<{ path?: string[] }> }) {
  return proxy(req, context)
}
