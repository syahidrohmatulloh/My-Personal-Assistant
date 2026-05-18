"use client"

import { type FormEvent, type ReactNode, useEffect, useState } from "react"
import { Save, UserRound } from "lucide-react"
import { getIdentity, putIdentity } from "@/lib/api"
import {
  AppHeaderAction,
  AppPageShell,
  AppPanel,
  AppStatCard,
  AppStatGrid,
} from "@/components/ui/app-page-shell"

type FormState = {
  name: string
  location: string
  role: string
  industry: string
  values: string
  communication: string
  timezone: string
  narrative: string
}

const EMPTY: FormState = {
  name: "",
  location: "",
  role: "",
  industry: "",
  values: "",
  communication: "",
  timezone: "",
  narrative: "",
}

const inputCls =
  "w-full rounded-2xl border border-slate-200/70 bg-white/80 px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
const textareaCls = inputCls + " resize-none"

function profileToForm(profile: Record<string, unknown>, narrative: string | null): FormState {
  const work = (profile.work ?? {}) as Record<string, unknown>
  const comm = (profile.communication_preferences ?? {}) as Record<string, unknown>
  const fallbackTz =
    typeof Intl !== "undefined"
      ? Intl.DateTimeFormat().resolvedOptions().timeZone
      : "UTC"

  return {
    name: (profile.name as string) ?? "",
    location: (profile.location as string) ?? "",
    role: (work.role as string) ?? "",
    industry: (work.industry as string) ?? "",
    values: Array.isArray(profile.values)
      ? (profile.values as string[]).join(", ")
      : "",
    communication: (comm.tone as string) ?? "",
    timezone: (profile.timezone as string) ?? fallbackTz,
    narrative: narrative ?? "",
  }
}

function formToProfile(f: FormState): {
  profile: Record<string, unknown>
  narrative: string | null
} {
  const profile: Record<string, unknown> = {}

  if (f.name) profile.name = f.name
  if (f.location) profile.location = f.location
  if (f.role || f.industry) {
    profile.work = {
      ...(f.role ? { role: f.role } : {}),
      ...(f.industry ? { industry: f.industry } : {}),
    }
  }
  if (f.values) {
    profile.values = f.values
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean)
  }
  if (f.communication) {
    profile.communication_preferences = { tone: f.communication }
  }
  if (f.timezone) {
    profile.timezone = f.timezone
  }

  return { profile, narrative: f.narrative || null }
}

export default function IdentityPage() {
  const [form, setForm] = useState<FormState>(EMPTY)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false

    getIdentity()
      .then((data) => {
        if (cancelled) return
        setForm(profileToForm(data.profile, data.narrative))
        setSavedAt(data.updated_at)
      })
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false))

    return () => {
      cancelled = true
    }
  }, [])

  async function handleSave(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)

    try {
      const { profile, narrative } = formToProfile(form)
      const updated = await putIdentity(profile, narrative)
      setSavedAt(updated.updated_at)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  function update<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  const filledFields = [
    form.name,
    form.location,
    form.role,
    form.industry,
    form.values,
    form.communication,
    form.timezone,
    form.narrative,
  ].filter((value) => value.trim()).length

  return (
    <AppPageShell
      eyebrow="Aliyya Identity"
      title="Who you are"
      description="The grounding Aliyya uses to understand you. Everything is optional, editable, and meant to make conversations more consistent."
      maxWidthClassName="max-w-5xl"
      actions={<AppHeaderAction href="/chat">Back to chat</AppHeaderAction>}
      stats={
        <AppStatGrid>
          <AppStatCard label="Profile fields" value={`${filledFields}/8`} icon={UserRound} />
          <AppStatCard label="Timezone" value={form.timezone || "—"} />
          <AppStatCard
            label="Last saved"
            value={savedAt ? new Date(savedAt).toLocaleDateString() : "—"}
          />
        </AppStatGrid>
      }
    >
      {loading ? (
        <AppPanel>
          <div className="p-6 text-sm text-slate-600 dark:text-zinc-300">Loading…</div>
        </AppPanel>
      ) : (
        <form
          onSubmit={handleSave}
          className="rounded-[1.5rem] border border-slate-200/70 bg-white/75 p-5 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] sm:p-6"
        >
          <div className="grid gap-5 lg:grid-cols-2">
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

            <Field label="Role">
              <input
                type="text"
                value={form.role}
                onChange={(e) => update("role", e.target.value)}
                placeholder="Founder, banker, designer, student…"
                className={inputCls}
              />
            </Field>

            <Field label="Industry / context">
              <input
                type="text"
                value={form.industry}
                onChange={(e) => update("industry", e.target.value)}
                placeholder="Banking, AI, consulting, etc."
                className={inputCls}
              />
            </Field>

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
              hint="So Aliyya gets dates and greetings right."
            >
              <input
                type="text"
                value={form.timezone}
                onChange={(e) => update("timezone", e.target.value)}
                placeholder="Asia/Jakarta"
                className={inputCls}
              />
            </Field>

            <div className="lg:col-span-2">
              <Field
                label="Anything else worth knowing"
                hint="A few sentences of context."
              >
                <textarea
                  value={form.narrative}
                  onChange={(e) => update("narrative", e.target.value)}
                  rows={5}
                  placeholder="I'm building an AI assistant alongside my main work. I tend to prefer direct, practical help."
                  className={textareaCls}
                />
              </Field>
            </div>
          </div>

          {error ? (
            <p className="mt-5 text-sm text-red-700 dark:text-red-300">{error}</p>
          ) : null}

          <div className="mt-6 flex flex-col gap-3 border-t border-slate-200/70 pt-4 dark:border-white/10 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-slate-500 dark:text-zinc-500">
              {savedAt ? `Last saved ${new Date(savedAt).toLocaleString()}` : "Not saved yet"}
            </p>
            <button
              type="submit"
              disabled={saving}
              className="inline-flex min-h-10 w-full items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:opacity-50 active:scale-[0.98] sm:w-auto"
            >
              <Save className="h-3.5 w-3.5" strokeWidth={2.5} />
              {saving ? "Saving…" : "Save identity"}
            </button>
          </div>
        </form>
      )}
    </AppPageShell>
  )
}

function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="block">
      <span className="text-sm font-medium text-slate-900 dark:text-white">
        {label}
      </span>
      {hint ? (
        <span className="mt-0.5 block text-xs text-slate-500 dark:text-zinc-400">
          {hint}
        </span>
      ) : null}
      <div className="mt-2">{children}</div>
    </label>
  )
}
