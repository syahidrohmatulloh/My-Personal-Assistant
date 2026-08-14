import {
  createServerClient,
  type CookieOptions,
} from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

type CookieToSet = {
  name: string;
  value: string;
  options?: CookieOptions;
};

export async function middleware(request: NextRequest) {
  let response = NextResponse.next({ request });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: CookieToSet[]) {
          cookiesToSet.forEach(({ name, value }) => {
            request.cookies.set(name, value);
          });
          response = NextResponse.next({ request });
          cookiesToSet.forEach(({ name, value, options }) => {
            response.cookies.set(name, value, options);
          });
        },
      },
    },
  );

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;
  const isAuthRoute = pathname === "/login" || pathname === "/signup";
  const isProtectedRoute =
    pathname.startsWith("/chat") ||
    pathname.startsWith("/chat-v2") ||
    pathname.startsWith("/calendar") ||
    pathname.startsWith("/memories") ||
    pathname.startsWith("/identity") ||
    pathname.startsWith("/journal") ||
    pathname.startsWith("/goals") ||
    pathname.startsWith("/people") ||
    pathname.startsWith("/welcome") ||
    pathname.startsWith("/settings");

  if (!user && isProtectedRoute) {
    return NextResponse.redirect(new URL("/login", request.url));
  }
  if (user && isAuthRoute) {
    return NextResponse.redirect(new URL("/home", request.url));
  }

  return response;
}

// Narrow matcher — only run on routes that actually need auth checks.
// Skips /api/*, /_next/*, /, static files, etc.
export const config = {
  matcher: [
    "/chat/:path*",
    "/chat-v2/:path*",
    "/calendar/:path*",
    "/memories/:path*",
    "/identity/:path*",
    "/journal/:path*",
    "/goals/:path*",
    "/people/:path*",
    "/welcome/:path*",
    "/settings/:path*",
    "/login",
    "/signup",
  ],
};
