"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft, Save } from "lucide-react";
import { getIdentity, putIdentity } from "@/lib/api";
import { BackToChatButton } from "@/components/settings/back-to-chat-button";

type FormState = {
  name: string;
  location: string;
  role: string;
  industry: string;
  values: string;
  communication: string;
  timezone: string;
  narrative: string;
};

const EMPTY: FormState = {
  name: "",
  location: "",
  role: "",
  industry: "",
  values: "",
  communication: "",
  timezone: "",
  narrative: "",
};

function profileToForm(profile: Record<string, unknown>, narrative: string | null): FormState {
  const work = (profile.work ?? {}) as Record<string, unknown>;
  const comm = (profile.communication_preferences ?? {}) as Record<string, unknown>;
  // Default to the browser's timezone if user hasn't set one.
  const fallbackTz =
    typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "UTC";
  return {
    name: (profile.name as string) ?? "",
    location: (profile.location as string) ?? "",
    role: (work.role as string) ?? "",
    industry: (work.industry as string) ?? "",
    values: Array.isArray(profile.values) ? (profile.values as string[]).join(", ") : "",
    communication: (comm.tone as string) ?? "",
    timezone: (profile.timezone as string) ?? fallbackTz,
    narrative: narrative ?? "",
  };
}

function formToProfile(f: FormState): { profile: Record<string, unknown>; narrative: string | null } {
  const profile: Record<string, unknown> = {};
  if (f.name) profile.name = f.name;
  if (f.location) profile.location = f.location;
  if (f.role || f.industry) {
    profile.work = {
      ...(f.role ? { role: f.role } : {}),
      ...(f.industry ? { industry: f.industry } : {}),
    };
  }
  if (f.values) {
    profile.values = f.values
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
  }
  if (f.communication) {
    profile.communication_preferences = { tone: f.communication };
  }
  if (f.timezone) {
    profile.timezone = f.timezone;
  }
  return { profile, narrative: f.narrative || null };
}

export default function IdentityPage() {
  const [form, setForm] = useState<FormState>(EMPTY);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getIdentity()
      .then((data) => {
        if (cancelled) return;
        setForm(profileToForm(data.profile, data.narrative));
        setSavedAt(data.updated_at);
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, []);

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const { profile, narrative } = formToProfile(form);
      const updated = await putIdentity(profile, narrative);
      setSavedAt(updated.updated_at);
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  }

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  return (
    <main className="min-h-dvh">
      <div className="max-w-2xl mx-auto px-4 sm:px-6 py-5 sm:py-8 fade-up">
        <BackToChatButton />

        <h1 className="text-3xl font-semibold text-fg mb-1 tracking-tighter">Who you are</h1>
        <p className="text-base text-fg-muted mb-8">
          The grounding the assistant uses to know you. Everything is optional. Edit anytime.
        </p>

        {loading ? (
          <p className="text-sm text-fg-muted">Loading…</p>
        ) : (
          <form onSubmit={handleSave} className="glass rounded-2xl p-6 space-y-5">
            <Field label="Name">
              <input
                type="text"
                value={form.name}
                onChange={(e) => update("name", e.target.value)}
                placeholder="What should I call you?"
                className={inputCls}
              />
            </Field>

            <Field label="Location">
              <input
                type="text"
                value={form.location}
                onChange={(e) => update("location", e.target.value)}
                placeholder="Jakarta, Indonesia"
                className={inputCls}
              />
            </Field>

            <div className="grid sm:grid-cols-2 gap-4">
              <Field label="Role">
                <input
                  type="text"
                  value={form.role}
                  onChange={(e) => update("role", e.target.value)}
                  placeholder="Founder, designer, student…"
                  className={inputCls}
                />
              </Field>
              <Field label="Industry / context">
                <input
                  type="text"
                  value={form.industry}
                  onChange={(e) => update("industry", e.target.value)}
                  placeholder="AI startup, healthcare, etc."
                  className={inputCls}
                />
              </Field>
            </div>

            <Field
              label="Values"
              hint="A few things that matter to you, comma-separated."
            >
              <input
                type="text"
                value={form.values}
                onChange={(e) => update("values", e.target.value)}
                placeholder="honesty, growth, family"
                className={inputCls}
              />
            </Field>

            <Field
              label="How you'd like me to communicate"
              hint="Short description of the tone you prefer."
            >
              <input
                type="text"
                value={form.communication}
                onChange={(e) => update("communication", e.target.value)}
                placeholder="Warm but direct. Don't soften hard truths."
                className={inputCls}
              />
            </Field>

            <Field
              label="Your timezone"
              hint="So I get dates right in our conversations. Defaults to your browser's timezone."
            >
              <input
                type="text"
                value={form.timezone}
                onChange={(e) => update("timezone", e.target.value)}
                placeholder="Asia/Jakarta"
                className={inputCls}
              />
            </Field>

            <Field
              label="Anything else worth knowing"
              hint="A few sentences of context."
            >
              <textarea
                value={form.narrative}
                onChange={(e) => update("narrative", e.target.value)}
                rows={5}
                placeholder="I'm building an AI assistant alongside my main work. I tend to be most clear-headed in the morning."
                className={textareaCls}
              />
            </Field>

            {error && <p className="text-sm text-danger">{error}</p>}

            <div className="flex items-center justify-between pt-2 border-t border-border">
              <p className="text-xs text-fg-subtle">
                {savedAt ? `Last saved ${new Date(savedAt).toLocaleString()}` : "Not saved yet"}
              </p>
              <button
                type="submit"
                disabled={saving}
                className="inline-flex items-center gap-1.5 rounded-xl bg-accent text-on-accent px-4 py-2 text-sm font-medium hover:bg-accent-hover disabled:opacity-50 transition-all active:scale-[0.98] shadow-md shadow-accent/25"
              >
                <Save className="h-3.5 w-3.5" strokeWidth={2.5} />
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </form>
        )}
      </div>
    </main>
  );
}

const inputCls =
  "w-full rounded-xl border border-border-strong bg-bg/40 backdrop-blur-sm px-3 py-2 text-sm text-fg placeholder:text-fg-subtle focus:outline-none focus:border-accent focus:ring-2 focus:ring-accent/20 transition-all";
const textareaCls = inputCls + " resize-none";

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-fg">{label}</span>
      {hint && <span className="block text-xs text-fg-muted mt-0.5">{hint}</span>}
      <div className="mt-2">{children}</div>
    </label>
  );
}
