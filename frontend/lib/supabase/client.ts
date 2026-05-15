"use client";

import { createBrowserClient } from "@supabase/ssr";

/**
 * Supabase client for use in client components.
 *
 * Reads the user's session from cookies, so calling `supabase.auth.getUser()`
 * works on every page after login.
 */
export function createClient() {
  return createBrowserClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
  );
}
