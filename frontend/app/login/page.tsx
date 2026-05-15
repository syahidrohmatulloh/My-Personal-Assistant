"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Sparkles } from "lucide-react";
import { createClient } from "@/lib/supabase/client";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);

    const supabase = createClient();
    const { error } = await supabase.auth.signInWithPassword({ email, password });

    if (error) {
      setError(error.message);
      setLoading(false);
      return;
    }

    router.push("/chat");
    router.refresh();
  }

  return (
    <main className="min-h-dvh grid place-items-center px-5 sm:px-6 py-8">
      <div className="w-full max-w-sm fade-up">
        {/* Brand */}
        <div className="flex flex-col items-center mb-8">
          <div className="h-12 w-12 rounded-2xl bg-accent grid place-items-center shadow-xl shadow-accent/30 mb-3">
            <Sparkles className="h-5 w-5 text-on-accent" strokeWidth={2.2} />
          </div>
          <h1 className="text-2xl font-semibold text-fg tracking-tighter">Welcome back</h1>
          <p className="text-sm text-fg-muted mt-1">Sign in to your assistant.</p>
        </div>

        <form onSubmit={handleSubmit} className="glass rounded-2xl p-6 space-y-4">
          <label className="block">
            <span className="text-sm font-medium text-fg">Email</span>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={inputCls}
            />
          </label>

          <label className="block">
            <span className="text-sm font-medium text-fg">Password</span>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputCls}
            />
          </label>

          {error && <p className="text-sm text-danger">{error}</p>}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-accent text-on-accent py-2.5 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all active:scale-[0.98] shadow-md shadow-accent/25"
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>

        <p className="text-sm text-fg-muted mt-6 text-center">
          Don&apos;t have an account?{" "}
          <Link href="/signup" className="text-accent font-medium hover:text-accent-hover">
            Sign up
          </Link>
        </p>
      </div>
    </main>
  );
}

const inputCls =
  "mt-1.5 w-full rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all";
