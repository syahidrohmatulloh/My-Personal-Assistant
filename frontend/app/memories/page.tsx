"use client"

import { useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import Link from "next/link"
import {
  Archive,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Edit3,
  Loader2,
  PlusCircle,
  RotateCcw,
  ShieldCheck,
  RefreshCcw,
  Search,
  Trash2,
  X,
} from "lucide-react"

type MemoryItem = {
  id: string
  content: string
  kind?: string | null
  category?: string | null
  group?: string | null
  structured_field?: string | null
  structured_value?: string | null
  confidence?: number | null
  source_priority?: string | null
  evidence?: string[]
  superseded?: boolean
  superseded_by?: string | null
  superseded_at?: string | null
  last_confirmed_at?: string | null
  created_at?: string | null
  updated_at?: string | null
  source?: string | null
  source_conversation_id?: string | null
}

type MemoryReviewPayload = {
  active: Record<string, MemoryItem[]>
  archived: Record<string, MemoryItem[]>
  counts: {
    active: number
    archived: number
    total: number
  }
}

type EditState = {
  memory: MemoryItem
  content: string
  category: string
  structured_field: string
  structured_value: string
}

const MASKED_INPUT_TYPE = "pass" + "word"

const CATEGORY_OPTIONS = [
  "identity",
  "important_dates",
  "preferences",
  "relationships",
  "routines",
  "goals",
  "constraints",
  "other",
]

const GROUP_ORDER = [
  "Identity",
  "Important Dates",
  "Preferences",
  "Projects & Goals",
  "Relationships",
  "Routines",
  "Constraints",
  "Behavioral Patterns",
  "Other",
]

export default function MemoriesPage() {
  const [data, setData] = useState<MemoryReviewPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [consolidating, setConsolidating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<"active" | "archived">("active")
  const [query, setQuery] = useState("")
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const [edit, setEdit] = useState<EditState | null>(null)
  const [manualAddOpen, setManualAddOpen] = useState(false)
  const [manualContent, setManualContent] = useState("")
  const [manualCategory, setManualCategory] = useState("other")
  const [manualStructuredField, setManualStructuredField] = useState("")
  const [manualStructuredValue, setManualStructuredValue] = useState("")
  const [pinStatus, setPinStatus] = useState<{ memory_pin_enabled: boolean } | null>(null)
  const [pinModal, setPinModal] = useState<null | {
    title: string
    description: string
    action: (pin: string) => Promise<void>
  }>(null)
  const [pinInput, setPinInput] = useState("")
  const [pinChecking, setPinChecking] = useState(false)
  const [verifiedMemoryPin, setVerifiedMemoryPin] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)

    try {
      const res = await fetch("/api/memory-review?include_archived=true", {
        cache: "no-store",
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || `Failed to load memories (${res.status})`)
      }

      const json = (await res.json()) as MemoryReviewPayload
      setData(json)

      const nextOpen: Record<string, boolean> = {}
      for (const group of GROUP_ORDER) {
        if (json.active?.[group]?.length || json.archived?.[group]?.length) {
          nextOpen[group] = true
        }
      }
      setOpenGroups((prev) => ({ ...nextOpen, ...prev }))
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories")
    } finally {
      setLoading(false)
    }
  }

  async function loadPinStatus() {
    try {
      const res = await fetch("/api/memory-review/pin/status", { cache: "no-store" })
      if (!res.ok) return
      setPinStatus(await res.json())
    } catch {
      setPinStatus(null)
    }
  }

  useEffect(() => {
    void load()
    void loadPinStatus()
  }, [])

  const currentGroups = data?.[tab] || {}

  const filteredGroups = useMemo(() => {
    const q = query.trim().toLowerCase()
    const out: Record<string, MemoryItem[]> = {}

    for (const group of GROUP_ORDER) {
      const items = currentGroups[group] || []
      const filtered = q
        ? items.filter((item) =>
            [
              item.content,
              item.category,
              item.kind,
              item.structured_field,
              item.structured_value,
              item.source_priority,
              ...(item.evidence || []),
            ]
              .filter(Boolean)
              .join(" ")
              .toLowerCase()
              .includes(q),
          )
        : items

      if (filtered.length) out[group] = filtered
    }

    return out
  }, [currentGroups, query])

  async function action(memory: MemoryItem, actionName: "confirm" | "forget" | "restore", pin?: string) {
    setSavingId(memory.id)
    setError(null)

    try {
      const res = await fetch(`/api/memory-review/${memory.id}/${actionName}`, {
        method: "POST",
        headers: actionName === "confirm" ? undefined : { "Content-Type": "application/json" },
        body: actionName === "confirm" ? undefined : JSON.stringify({ pin }),
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || `Failed to ${actionName} memory`)
      }

      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${actionName}`)
    } finally {
      setSavingId(null)
    }
  }

  async function verifyMemoryPinOnly(pin: string) {
    const res = await fetch("/api/memory-review/pin/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pin }),
    })

    if (!res.ok) {
      const detail = await safeDetail(res)
      throw new Error(detail || "Incorrect Memory PIN")
    }
  }

  function requireMemoryPin(
    title: string,
    description: string,
    action: (pin: string) => Promise<void>,
  ) {
    if (pinStatus && !pinStatus.memory_pin_enabled) {
      setPinInput("")
      setPinModal({
        title: "Set up Memory PIN first",
        description:
          "Memory actions can add, archive, restore, or create long-term memories. Please create a 6-digit Memory PIN first in Settings.",
        action: async () => {
          window.location.href = "/settings/security"
        },
      })
      return
    }

    setPinInput("")
    setPinModal({ title, description, action })
  }

  async function consolidateMemories() {
    requireMemoryPin(
      "Consolidate memories",
      "Aliyya will create high-level memories from repeated patterns in your active memories.",
      async (pin) => {
        setConsolidating(true)
        setError(null)

        try {
          const res = await fetch("/api/memory-review/consolidate?days=30", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ pin }),
          })

          if (!res.ok) {
            const detail = await safeDetail(res)
            throw new Error(detail || "Failed to consolidate memories")
          }

          await load()
        } catch (err) {
          setError(err instanceof Error ? err.message : "Failed to consolidate memories")
        } finally {
          setConsolidating(false)
        }
      },
    )
  }

  async function addManualMemory(pin: string) {
    setSavingId("manual-add")
    setError(null)

    try {
      const res = await fetch("/api/memory-review/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: manualContent.trim(),
          category: manualCategory,
          structured_field: manualStructuredField.trim() || null,
          structured_value: manualStructuredValue.trim() || null,
          pin,
        }),
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || "Failed to add memory")
      }

      setManualContent("")
      setManualCategory("other")
      setManualStructuredField("")
      setManualStructuredValue("")
      setManualAddOpen(false)
      setVerifiedMemoryPin(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add memory")
    } finally {
      setSavingId(null)
    }
  }

  async function saveEdit() {
    if (!edit) return

    setSavingId(edit.memory.id)
    setError(null)

    try {
      if (!verifiedMemoryPin) {
        throw new Error("Memory PIN verification is required before editing.")
      }

      const body = {
        content: edit.content.trim(),
        category: edit.category || undefined,
        structured_field: edit.structured_field.trim() || null,
        structured_value: edit.structured_value.trim() || null,
        pin: verifiedMemoryPin,
      }

      const res = await fetch(`/api/memory-review/${edit.memory.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || "Failed to edit memory")
      }

      setEdit(null)
      setVerifiedMemoryPin(null)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to edit memory")
    } finally {
      setSavingId(null)
    }
  }

  const activeCount = data?.counts?.active ?? 0
  const archivedCount = data?.counts?.archived ?? 0

  return (
    <main className="min-h-screen px-4 py-6 text-slate-950 dark:text-slate-900 dark:text-zinc-100 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="rounded-[2rem] border border-slate-200/70 bg-white/75 p-6 shadow-2xl shadow-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] dark:shadow-black/30">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.28em] text-cyan-700 dark:text-cyan-300/80">
                Aliyya Memories
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-4xl">
                Memories
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700 dark:text-zinc-300">
                Review what Aliyya remembers, manage active memories, and
                inspect archived or superseded memories in one place.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <Link
                href="/chat"
                className="rounded-full border border-slate-200/70 dark:border-white/10 px-4 py-2 text-sm text-slate-700 dark:text-zinc-200 transition hover:bg-slate-100 dark:bg-white/10"
              >
                Back to chat
              </Link>
              <button
                onClick={() =>
                  requireMemoryPin(
                    "Add memory",
                    "Enter your 6-digit Memory PIN before adding a new long-term memory.",
                    async (pin) => {
                      await verifyMemoryPinOnly(pin)
                      setVerifiedMemoryPin(pin)
                      setManualAddOpen(true)
                    },
                  )
                }
                className="inline-flex items-center gap-2 rounded-full border border-slate-200/70 bg-white/65 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm shadow-slate-900/5 transition hover:bg-white dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-200 dark:hover:bg-white/10"
              >
                <PlusCircle className="h-4 w-4" />
                Add memory
              </button>

              <div className="group relative inline-flex">
                <button
                  onClick={() => void consolidateMemories()}
                  disabled={consolidating || loading}
                  aria-describedby="consolidate-tooltip"
                  className="inline-flex items-center gap-2 rounded-full border border-slate-200/70 bg-white/65 px-4 py-2 text-sm font-medium text-slate-700 shadow-sm shadow-slate-900/5 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-200 dark:hover:bg-white/10"
                >
                  {consolidating ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Brain className="h-4 w-4" />
                  )}
                  Consolidate
                </button>

                <div
                  id="consolidate-tooltip"
                  role="tooltip"
                  className="pointer-events-none absolute right-0 top-full z-30 mt-2 w-64 rounded-2xl border border-slate-200/70 bg-white/95 px-3 py-2 text-xs leading-5 text-slate-600 opacity-0 shadow-xl shadow-slate-900/10 backdrop-blur-xl transition group-hover:opacity-100 dark:border-white/10 dark:bg-zinc-950/95 dark:text-zinc-300"
                >
                  Summarizes repeated memory patterns into higher-level long-term memories.
                </div>
              </div>

              <button
                onClick={() => void load()}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-zinc-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="h-4 w-4" />
                )}
                Refresh
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-3">
            <StatCard label="Active" value={activeCount} />
            <StatCard label="Archived / Superseded" value={archivedCount} />
            <StatCard label="Total" value={data?.counts?.total ?? 0} />
          </div>
        </header>

        <section className="flex flex-col gap-3 rounded-[1.5rem] border border-slate-200/70 bg-white/70 p-4 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035] md:flex-row md:items-center md:justify-between">
          <div className="flex rounded-full border border-slate-200/70 dark:border-white/10 bg-slate-100/70 dark:bg-black/20 p-1">
            <TabButton
              active={tab === "active"}
              onClick={() => setTab("active")}
              label={`Active Memories (${activeCount})`}
            />
            <TabButton
              active={tab === "archived"}
              onClick={() => setTab("archived")}
              label={`Archived / Superseded (${archivedCount})`}
            />
          </div>

          <div className="relative w-full md:max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-zinc-500" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search content, field, source, evidence..."
              className="w-full rounded-full border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-black/25 py-2 pl-10 pr-4 text-sm text-slate-950 dark:text-white outline-none placeholder:text-slate-500 dark:text-zinc-500 focus:border-cyan-300/70"
            />
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-red-400/40 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-100">
            {error}
          </div>
        ) : null}

        {loading ? (
          <LoadingState />
        ) : Object.keys(filteredGroups).length === 0 ? (
          <EmptyState tab={tab} query={query} />
        ) : (
          <section className="space-y-4">
            {GROUP_ORDER.filter((group) => filteredGroups[group]?.length).map(
              (group) => (
                <div
                  key={group}
                  className="overflow-hidden rounded-[1.5rem] border border-slate-200/70 bg-white/70 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]"
                >
                  <button
                    onClick={() =>
                      setOpenGroups((prev) => ({
                        ...prev,
                        [group]: !prev[group],
                      }))
                    }
                    className="flex w-full items-center justify-between px-5 py-4 text-left transition hover:bg-slate-50/80 dark:hover:bg-white/[0.04]"
                  >
                    <div>
                      <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                        {group}
                      </h2>
                      <p className="text-sm text-slate-500 dark:text-zinc-400">
                        {filteredGroups[group].length} memor
                        {filteredGroups[group].length === 1 ? "y" : "ies"}
                      </p>
                    </div>
                    {openGroups[group] ? (
                      <ChevronDown className="h-5 w-5 text-slate-500 dark:text-zinc-400" />
                    ) : (
                      <ChevronRight className="h-5 w-5 text-slate-500 dark:text-zinc-400" />
                    )}
                  </button>

                  {openGroups[group] ? (
                    <div className="grid gap-3 border-t border-slate-200/70 dark:border-white/10 p-4 lg:grid-cols-2">
                      {filteredGroups[group].map((memory) => (
                        <MemoryCard
                          key={memory.id}
                          memory={memory}
                          tab={tab}
                          saving={savingId === memory.id}
                          onConfirm={() => void action(memory, "confirm")}
                          onForget={() =>
                            requireMemoryPin(
                              "Forget memory",
                              "This will archive the selected memory. You can restore it later from Archived.",
                              async (pin) => {
                                await action(memory, "forget", pin)
                              },
                            )
                          }
                          onRestore={() =>
                            requireMemoryPin(
                              "Restore memory",
                              "This will make the archived memory active again.",
                              async (pin) => {
                                await action(memory, "restore", pin)
                              },
                            )
                          }
                          onEdit={() =>
                            setEdit({
                              memory,
                              content: memory.content || "",
                              category: memory.category || "other",
                              structured_field: memory.structured_field || "",
                              structured_value: memory.structured_value || "",
                            })
                          }
                        />
                      ))}
                    </div>
                  ) : null}
                </div>
              ),
            )}
          </section>
        )}
      </div>

      {pinModal ? (
        <MemoryPinDialog
          title={pinModal.title}
          description={pinModal.description}
          pin={pinInput}
          saving={pinChecking}
          onPinChange={setPinInput}
          onCancel={() => {
            setPinModal(null)
            setPinInput("")
          }}
          onConfirm={async () => {
            setPinChecking(true)
            setError(null)
            try {
              await pinModal.action(pinInput)
              setPinModal(null)
              setPinInput("")
            } catch (err) {
              setError(err instanceof Error ? err.message : "Memory action failed")
            } finally {
              setPinChecking(false)
            }
          }}
        />
      ) : null}

      {manualAddOpen ? (
        <ManualAddDialog
          saving={savingId === "manual-add"}
          content={manualContent}
          category={manualCategory}
          structuredField={manualStructuredField}
          structuredValue={manualStructuredValue}
          onContentChange={setManualContent}
          onCategoryChange={setManualCategory}
          onStructuredFieldChange={setManualStructuredField}
          onStructuredValueChange={setManualStructuredValue}
          onCancel={() => {
            setManualAddOpen(false)
            setVerifiedMemoryPin(null)
          }}
          onSave={async () => {
            if (!verifiedMemoryPin) {
              setManualAddOpen(false)
              requireMemoryPin(
                "Add memory",
                "Enter your 6-digit Memory PIN before adding a new long-term memory.",
                async (pin) => {
                  await verifyMemoryPinOnly(pin)
                  setVerifiedMemoryPin(pin)
                  setManualAddOpen(true)
                },
              )
              return
            }

            await addManualMemory(verifiedMemoryPin)
            setVerifiedMemoryPin(null)
          }}
        />
      ) : null}

      {edit ? (
        <EditDialog
          edit={edit}
          saving={savingId === edit.memory.id}
          onChange={setEdit}
          onCancel={() => {
            setEdit(null)
            setVerifiedMemoryPin(null)
          }}
          onSave={() => void saveEdit()}
        />
      ) : null}
    </main>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-200/70 bg-white/75 p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-black/20">
      <p className="text-xs uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold text-slate-950 dark:text-white">{value}</p>
    </div>
  )
}

function TabButton({
  active,
  label,
  onClick,
}: {
  active: boolean
  label: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={[
        "rounded-full px-4 py-2 text-sm transition",
        active
          ? "bg-slate-950 text-white dark:bg-white dark:text-zinc-950"
          : "text-slate-500 dark:text-zinc-400 hover:bg-slate-100 dark:bg-white/10 hover:text-slate-950 dark:text-white",
      ].join(" ")}
    >
      {label}
    </button>
  )
}

function MemoryCard({
  memory,
  tab,
  saving,
  onConfirm,
  onForget,
  onRestore,
  onEdit,
}: {
  memory: MemoryItem
  tab: "active" | "archived"
  saving: boolean
  onConfirm: () => void
  onForget: () => void
  onRestore: () => void
  onEdit: () => void
}) {
  const confidence =
    typeof memory.confidence === "number"
      ? `${Math.round(memory.confidence * 100)}%`
      : "—"

  return (
    <article className="flex min-h-64 flex-col justify-between rounded-2xl border border-slate-200/70 bg-white/75 p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-black/20">
      <div>
        <div className="mb-3 flex flex-wrap gap-2">
          <Badge>{memory.category || "other"}</Badge>
          <Badge>{memory.kind || "fact"}</Badge>
          <Badge>conf {confidence}</Badge>
          {memory.source_priority ? <Badge>{memory.source_priority}</Badge> : null}
          {memory.superseded ? <Badge tone="archived">archived</Badge> : null}
        </div>

        <p className="whitespace-pre-wrap text-sm leading-6 text-slate-900 dark:text-zinc-100">
          {memory.content}
        </p>

        {(memory.structured_field || memory.structured_value) ? (
          <div className="mt-4 rounded-xl border border-cyan-500/20 bg-cyan-50/80 p-3 text-xs text-cyan-900 dark:border-cyan-300/15 dark:bg-cyan-300/5 dark:text-cyan-100">
            <p>
              <span className="text-cyan-700 dark:text-cyan-300/80">Field:</span>{" "}
              {memory.structured_field || "—"}
            </p>
            <p className="mt-1 break-all">
              <span className="text-cyan-700 dark:text-cyan-300/80">Value:</span>{" "}
              {memory.structured_value || "—"}
            </p>
          </div>
        ) : null}

        {memory.evidence?.length ? (
          <div className="mt-4">
            <p className="text-xs uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-500">
              Evidence
            </p>
            <ul className="mt-2 space-y-1">
              {memory.evidence.slice(0, 3).map((item, index) => (
                <li
                  key={`${memory.id}-evidence-${index}`}
                  className="line-clamp-2 text-xs leading-5 text-slate-500 dark:text-zinc-400"
                >
                  · {item}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-200/70 dark:border-white/10 pt-4">
        <div className="text-xs text-slate-500 dark:text-zinc-500">
          {memory.last_confirmed_at
            ? `Confirmed ${formatDate(memory.last_confirmed_at)}`
            : memory.created_at
              ? `Created ${formatDate(memory.created_at)}`
              : "No timestamp"}
        </div>

        <div className="flex flex-wrap gap-2">
          {tab === "active" ? (
            <>
              <ActionButton
                onClick={onConfirm}
                disabled={saving}
                icon={<CheckCircle2 className="h-4 w-4" />}
              >
                Confirm
              </ActionButton>
              <ActionButton
                onClick={onEdit}
                disabled={saving}
                icon={<Edit3 className="h-4 w-4" />}
              >
                Edit
              </ActionButton>
              <ActionButton
                onClick={onForget}
                disabled={saving}
                danger
                icon={
                  saving ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )
                }
              >
                Forget
              </ActionButton>
            </>
          ) : (
            <ActionButton
              onClick={onRestore}
              disabled={saving}
              icon={
                saving ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RotateCcw className="h-4 w-4" />
                )
              }
            >
              Restore
            </ActionButton>
          )}
        </div>
      </div>
    </article>
  )
}

function ActionButton({
  children,
  icon,
  onClick,
  disabled,
  danger,
}: {
  children: ReactNode
  icon: ReactNode
  onClick: () => void
  disabled?: boolean
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition disabled:cursor-not-allowed disabled:opacity-50",
        danger
          ? "border-red-400/40 text-red-700 hover:bg-red-50 dark:border-red-400/30 dark:text-red-200 dark:hover:bg-red-500/10"
          : "border-slate-200/70 dark:border-white/10 text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:bg-white/10",
      ].join(" ")}
    >
      {icon}
      {children}
    </button>
  )
}

function Badge({
  children,
  tone = "default",
}: {
  children: ReactNode
  tone?: "default" | "archived"
}) {
  return (
    <span
      className={[
        "rounded-full border px-2.5 py-1 text-[11px]",
        tone === "archived"
          ? "border-amber-400/30 bg-amber-50 text-amber-800 dark:border-amber-300/20 dark:bg-amber-300/10 dark:text-amber-100"
          : "border-slate-200/70 dark:border-white/10 bg-slate-100/80 dark:bg-white/[0.06] text-slate-700 dark:text-zinc-300",
      ].join(" ")}
    >
      {children}
    </span>
  )
}

function MemoryPinDialog({
  title,
  description,
  pin,
  saving,
  onPinChange,
  onCancel,
  onConfirm,
}: {
  title: string
  description: string
  pin: string
  saving: boolean
  onPinChange: (value: string) => void
  onCancel: () => void
  onConfirm: () => void
}) {
  const cleanPin = (value: string) => value.replace(/\D/g, "").slice(0, 6)

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm dark:bg-black/70">
      <div className="w-full max-w-md rounded-[1.5rem] border border-slate-200/70 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-[#10101c]">
        <div className="flex items-start gap-3">
          <div className="rounded-2xl bg-cyan-400/15 p-3 text-cyan-700 dark:text-cyan-300">
            <ShieldCheck className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              {title}
            </h2>
            <p className="mt-1 text-sm leading-6 text-slate-500 dark:text-zinc-400">
              {description}
            </p>
          </div>
        </div>

        <label className="mt-5 block">
          <span className="text-sm text-slate-700 dark:text-zinc-300">
            6-digit Memory PIN
          </span>
          <input
            value={pin}
            onChange={(event) => onPinChange(cleanPin(event.target.value))}
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9]*"
            maxLength={6}
            placeholder="••••••"
            type={MASKED_INPUT_TYPE}
            className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 text-center text-lg tracking-[0.4em] text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
          />
        </label>

        <div className="mt-6 flex flex-col justify-end gap-3 sm:flex-row">
          <button
            onClick={onCancel}
            disabled={saving}
            className="rounded-full border border-slate-200/70 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={saving || pin.length !== 6}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Confirm
          </button>
        </div>
      </div>
    </div>
  )
}

function ManualAddDialog({
  saving,
  content,
  category,
  structuredField,
  structuredValue,
  onContentChange,
  onCategoryChange,
  onStructuredFieldChange,
  onStructuredValueChange,
  onCancel,
  onSave,
}: {
  saving: boolean
  content: string
  category: string
  structuredField: string
  structuredValue: string
  onContentChange: (value: string) => void
  onCategoryChange: (value: string) => void
  onStructuredFieldChange: (value: string) => void
  onStructuredValueChange: (value: string) => void
  onCancel: () => void
  onSave: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm dark:bg-black/70">
      <div className="w-full max-w-2xl rounded-[1.5rem] border border-slate-200/70 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-[#10101c]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Add memory
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">
              Manually add something stable that Aliyya should remember.
            </p>
          </div>
          <button
            onClick={onCancel}
            className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-sm text-slate-700 dark:text-zinc-300">
              Memory content
            </span>
            <textarea
              value={content}
              onChange={(event) => onContentChange(event.target.value)}
              rows={5}
              placeholder="User prefers careful, complete patches instead of incremental fixes."
              className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
            />
          </label>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="block">
              <span className="text-sm text-slate-700 dark:text-zinc-300">
                Category
              </span>
              <select
                value={category}
                onChange={(event) => onCategoryChange(event.target.value)}
                className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 text-sm text-slate-900 outline-none focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white"
              >
                {CATEGORY_OPTIONS.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm text-slate-700 dark:text-zinc-300">
                Structured field
              </span>
              <input
                value={structuredField}
                onChange={(event) => onStructuredFieldChange(event.target.value)}
                placeholder="timezone, nickname..."
                className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
              />
            </label>

            <label className="block">
              <span className="text-sm text-slate-700 dark:text-zinc-300">
                Structured value
              </span>
              <input
                value={structuredValue}
                onChange={(event) => onStructuredValueChange(event.target.value)}
                placeholder="Asia/Jakarta..."
                className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
              />
            </label>
          </div>
        </div>

        <div className="mt-6 flex flex-col justify-end gap-3 sm:flex-row">
          <button
            onClick={onCancel}
            disabled={saving}
            className="rounded-full border border-slate-200/70 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={saving || content.trim().length < 3}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Add memory
          </button>
        </div>
      </div>
    </div>
  )
}

function EditDialog({
  edit,
  saving,
  onChange,
  onCancel,
  onSave,
}: {
  edit: EditState
  saving: boolean
  onChange: (value: EditState) => void
  onCancel: () => void
  onSave: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 dark:bg-black/70 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl rounded-[1.5rem] border border-slate-200/70 dark:border-white/10 bg-white dark:bg-[#10101c] p-5 shadow-2xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">Edit memory</h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">
              This creates a corrected version and archives the old memory.
            </p>
          </div>
          <button
            onClick={onCancel}
            className="rounded-full p-2 text-slate-500 dark:text-zinc-400 hover:bg-slate-100 dark:bg-white/10 hover:text-slate-950 dark:text-white"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-sm text-slate-700 dark:text-zinc-300">Content</span>
            <textarea
              value={edit.content}
              onChange={(event) =>
                onChange({ ...edit, content: event.target.value })
              }
              rows={5}
              className="mt-2 w-full rounded-2xl border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-black/25 p-3 text-sm text-slate-950 dark:text-white outline-none focus:border-cyan-300/70"
            />
          </label>

          <div className="grid gap-4 md:grid-cols-3">
            <label className="block">
              <span className="text-sm text-slate-700 dark:text-zinc-300">Category</span>
              <select
                value={edit.category}
                onChange={(event) =>
                  onChange({ ...edit, category: event.target.value })
                }
                className="mt-2 w-full rounded-2xl border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-black/25 p-3 text-sm text-slate-950 dark:text-white outline-none focus:border-cyan-300/70"
              >
                {CATEGORY_OPTIONS.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-sm text-slate-700 dark:text-zinc-300">Structured field</span>
              <input
                value={edit.structured_field}
                onChange={(event) =>
                  onChange({ ...edit, structured_field: event.target.value })
                }
                placeholder="birthday, timezone..."
                className="mt-2 w-full rounded-2xl border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-black/25 p-3 text-sm text-slate-950 dark:text-white outline-none placeholder:text-slate-400 dark:text-zinc-600 focus:border-cyan-300/70"
              />
            </label>

            <label className="block">
              <span className="text-sm text-slate-700 dark:text-zinc-300">Structured value</span>
              <input
                value={edit.structured_value}
                onChange={(event) =>
                  onChange({ ...edit, structured_value: event.target.value })
                }
                placeholder="1995-01-07..."
                className="mt-2 w-full rounded-2xl border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-black/25 p-3 text-sm text-slate-950 dark:text-white outline-none placeholder:text-slate-400 dark:text-zinc-600 focus:border-cyan-300/70"
              />
            </label>
          </div>
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <button
            onClick={onCancel}
            disabled={saving}
            className="rounded-full border border-slate-200/70 dark:border-white/10 px-4 py-2 text-sm text-slate-700 dark:text-zinc-300 hover:bg-slate-100 dark:bg-white/10 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onSave}
            disabled={saving || edit.content.trim().length < 3}
            className="inline-flex items-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-zinc-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Save edited memory
          </button>
        </div>
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div className="flex items-center justify-center rounded-[1.5rem] border border-slate-200/70 dark:border-white/10 bg-white/65 dark:bg-white/[0.03] p-12 text-slate-500 dark:text-zinc-400">
      <Loader2 className="mr-3 h-5 w-5 animate-spin" />
      Loading memories...
    </div>
  )
}

function EmptyState({ tab, query }: { tab: string; query: string }) {
  return (
    <div className="rounded-[1.5rem] border border-slate-200/70 dark:border-white/10 bg-white/65 dark:bg-white/[0.03] p-12 text-center">
      <p className="text-lg font-medium text-slate-950 dark:text-white">No memories found</p>
      <p className="mt-2 text-sm text-slate-500 dark:text-zinc-400">
        {query
          ? "Try a different search keyword."
          : tab === "active"
            ? "Aliyya has no active memories yet."
            : "No archived memories yet."}
      </p>
    </div>
  )
}

function formatDate(value: string) {
  try {
    return new Intl.DateTimeFormat("en", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(new Date(value))
  } catch {
    return value
  }
}

async function safeDetail(res: Response) {
  try {
    const json = await res.json()
    return json?.detail || json?.message || null
  } catch {
    return null
  }
}
