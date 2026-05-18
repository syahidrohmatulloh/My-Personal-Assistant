"use client"

import { type FormEvent, useEffect, useState } from "react"
import { Heart, Plus, Trash2, Users, X } from "lucide-react"
import {
  type Person,
  type PersonInput,
  createPerson,
  deletePerson,
  listPeople,
} from "@/lib/api"
import {
  AppHeaderAction,
  AppPageShell,
  AppPanel,
  AppStatCard,
  AppStatGrid,
} from "@/components/ui/app-page-shell"

const inputCls =
  "mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 px-3 py-2 text-sm text-slate-900 shadow-sm outline-none transition-all placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"

export default function PeoplePage() {
  const [people, setPeople] = useState<Person[]>([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [name, setName] = useState("")
  const [relationship, setRelationship] = useState("")
  const [importance, setImportance] = useState(5)
  const [emotional, setEmotional] = useState(5)
  const [birthday, setBirthday] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    let cancelled = false
    listPeople()
      .then((data) => !cancelled && setPeople(data))
      .catch((e) => !cancelled && setError(String(e)))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [])

  async function handleCreate(e: FormEvent) {
    e.preventDefault()
    if (!name.trim()) return

    setSaving(true)
    setError(null)

    try {
      const input: PersonInput = {
        name: name.trim(),
        relationship: relationship.trim() || null,
        importance,
        emotional_significance: emotional,
        birthday: birthday || null,
      }

      const created = await createPerson(input)
      setPeople((prev) =>
        [...prev, created].sort((a, b) => b.importance - a.importance),
      )
      setName("")
      setRelationship("")
      setImportance(5)
      setEmotional(5)
      setBirthday("")
      setShowForm(false)
    } catch (e) {
      setError(String(e))
    } finally {
      setSaving(false)
    }
  }

  async function handleDelete(id: string) {
    if (!confirm("Remove this person from Aliyya's people list?")) return

    const prev = people
    setPeople((p) => p.filter((x) => x.id !== id))

    try {
      await deletePerson(id)
    } catch (e) {
      setPeople(prev)
      setError(String(e))
    }
  }

  const avgImportance = people.length
    ? Math.round(people.reduce((sum, p) => sum + p.importance, 0) / people.length)
    : 0

  const birthdays = people.filter((p) => p.birthday).length

  return (
    <AppPageShell
      eyebrow="Aliyya People"
      title="People"
      description="Add people Aliyya should remember, like family, friends, colleagues, or important contacts."
      maxWidthClassName="max-w-5xl"
      actions={
        <>
          <AppHeaderAction href="/chat">Back to chat</AppHeaderAction>
          <AppHeaderAction
            onClick={() => setShowForm((v) => !v)}
            variant="primary"
            icon={showForm ? <X className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
          >
            {showForm ? "Close form" : "Add person"}
          </AppHeaderAction>
        </>
      }
      stats={
        <AppStatGrid>
          <AppStatCard label="People" value={people.length} icon={Users} />
          <AppStatCard label="Average closeness" value={avgImportance ? `${avgImportance}/10` : "—"} />
          <AppStatCard label="Birthdays" value={birthdays} />
        </AppStatGrid>
      }
    >
      {showForm ? (
        <form onSubmit={handleCreate} className="rounded-[1.5rem] border border-slate-200/70 bg-white/75 p-5 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04]">
          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">Name</span>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Anna"
                className={inputCls}
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">How you know them</span>
              <input
                type="text"
                value={relationship}
                onChange={(e) => setRelationship(e.target.value)}
                placeholder="wife, friend, colleague, client…"
                className={inputCls}
              />
            </label>
          </div>

          <div className="mb-4 grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">
                How often they matter day to day ({importance}/10)
              </span>
              <span className="mt-0.5 block text-xs text-slate-500 dark:text-zinc-400">
                How often they come up in your daily life.
              </span>
              <input
                type="range"
                min={1}
                max={10}
                value={importance}
                onChange={(e) => setImportance(Number(e.target.value))}
                className="mt-3 w-full accent-cyan-400"
              />
            </label>

            <label className="block">
              <span className="text-sm font-medium text-slate-900 dark:text-white">
                How close are they to you? ({emotional}/10)
              </span>
              <span className="mt-0.5 block text-xs text-slate-500 dark:text-zinc-400">
                How personally important they are to you.
              </span>
              <input
                type="range"
                min={1}
                max={10}
                value={emotional}
                onChange={(e) => setEmotional(Number(e.target.value))}
                className="mt-3 w-full accent-cyan-400"
              />
            </label>
          </div>

          <label className="mb-4 block">
            <span className="text-sm font-medium text-slate-900 dark:text-white">
              Birthday, optional
            </span>
            <input
              type="date"
              value={birthday}
              onChange={(e) => setBirthday(e.target.value)}
              className={inputCls}
            />
          </label>

          <div className="flex flex-col gap-2 border-t border-slate-200/70 pt-4 dark:border-white/10 sm:flex-row sm:justify-end">
            <button
              type="button"
              onClick={() => setShowForm(false)}
              className="min-h-10 rounded-full border border-slate-200/70 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving || !name.trim()}
              className="inline-flex min-h-10 items-center justify-center rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:bg-cyan-300 disabled:opacity-50"
            >
              {saving ? "Saving…" : "Add person"}
            </button>
          </div>
        </form>
      ) : null}

      {error ? (
        <div className="rounded-2xl border border-red-400/40 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-100">
          {error}
        </div>
      ) : null}

      {loading ? (
        <AppPanel>
          <div className="p-6 text-sm text-slate-600 dark:text-zinc-300">Loading…</div>
        </AppPanel>
      ) : people.length === 0 ? (
        <AppPanel>
          <div className="py-12 text-center">
            <Users className="mx-auto mb-2 h-6 w-6 text-slate-400 opacity-70 dark:text-zinc-500" />
            <p className="text-sm text-slate-500 dark:text-zinc-400">No one added yet.</p>
            <p className="mt-1 text-xs text-slate-400 dark:text-zinc-500">
              Start with the few people closest to you.
            </p>
          </div>
        </AppPanel>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {people.map((person) => (
            <article
              key={person.id}
              className="group rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-lg shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-black/20"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <p className="break-words text-sm font-semibold text-slate-950 dark:text-white">
                    {person.name}
                  </p>
                  {person.relationship ? (
                    <p className="mt-1 text-xs text-slate-600 dark:text-zinc-400">
                      {person.relationship}
                    </p>
                  ) : null}

                  <div className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500 dark:text-zinc-400">
                    <span className="rounded-full border border-cyan-500/20 bg-cyan-50 px-2 py-1 text-[10px] font-medium text-cyan-800 dark:border-cyan-300/20 dark:bg-cyan-300/10 dark:text-cyan-100">
                      importance {person.importance}/10
                    </span>
                    <span className="inline-flex items-center gap-1 rounded-full border border-rose-400/20 bg-rose-50 px-2 py-1 text-[10px] font-medium text-rose-700 dark:border-rose-300/20 dark:bg-rose-300/10 dark:text-rose-100">
                      <Heart className="h-3 w-3" />
                      {person.emotional_significance}/10
                    </span>
                    {person.birthday ? (
                      <span>
                        🎂{" "}
                        {new Date(person.birthday).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                    ) : null}
                  </div>
                </div>

                <button
                  onClick={() => void handleDelete(person.id)}
                  className="rounded-full border border-red-400/40 p-2 text-red-700 opacity-100 transition hover:bg-red-50 dark:border-red-400/30 dark:text-red-200 dark:hover:bg-red-500/10 sm:opacity-0 sm:group-hover:opacity-100"
                  aria-label="Delete person"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </div>
            </article>
          ))}
        </div>
      )}
    </AppPageShell>
  )
}
