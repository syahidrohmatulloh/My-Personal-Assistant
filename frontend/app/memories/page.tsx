"use client";


import { useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import Link from "next/link"
import {
  Archive,
  AlertTriangle,
  Brain,
  CalendarDays,
  CheckCircle2,
  ClipboardCheck,
  ExternalLink,
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
import { useAssistantOwnedLabel } from "@/hooks/use-identity-owned-label";
import { useAssistantDisplayName } from "@/hooks/use-identity-owned-label";
import { BackToLastChat } from "@/components/navigation/back-to-last-chat";

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
  archived?: boolean
  archived_by?: string | null
  archived_at?: string | null
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

type MemoryQualityReviewMemory = {
  id: string
  content: string
  category?: string | null
  structured_field?: string | null
  structured_value?: string | null
}

type MemoryQualityReasonInfo = {
  main?: string
  field?: string | null
  values?: string[]
  reasons?: string[]
}

type MemoryQualityReviewItem = {
  issue_type: "duplicate" | "conflict" | "low_quality" | string
  severity: "low" | "medium" | "high" | string
  memory_ids: string[]
  title: string
  explanation: string
  suggested_action: string
  reason?: MemoryQualityReasonInfo | null
  memories?: MemoryQualityReviewMemory[]
}

type MemoryQualityPayload = {
  summary: {
    active_memories: number
    duplicate_groups: number
    conflict_groups: number
    low_quality_memories: number
    stale_memories?: number
    needs_review: number
  }
  review_items: MemoryQualityReviewItem[]
}

type MemoryHealthSchedulerStatus = {
  enabled?: boolean
  running?: boolean
  interval_minutes?: number
  last_started_at?: string | null
  last_finished_at?: string | null
  last_error?: string | null
  health_source?: "scheduler" | "live" | "none"
  user_summary?: {
    needs_review?: number
    duplicate_groups?: number
    conflict_groups?: number
    low_quality_memories?: number
    stale_memories?: number
  } | null
}


type CalendarCandidateItem = {
  id: string
  content?: string | null
  category?: string | null
  structured_field?: string | null
  structured_value?: string | null
  due_date?: string | null
  expires_at?: string | null
  calendar_candidate?: boolean
  calendar_event_status?: string | null
  calendar_event_title?: string | null
  calendar_event_date?: string | null
  calendar_event_all_day?: boolean
  google_calendar_event_id?: string | null
  google_calendar_event_link?: string | null
  google_calendar_id?: string | null
  calendar_synced_at?: string | null
  calendar_sync_error?: string | null
  created_at?: string | null
  source_conversation_id?: string | null
}

type CalendarCandidatesPayload = {
  items: CalendarCandidateItem[]
  count: number
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

const CATEGORY_LABELS: Record<string, string> = {
  identity: "Identity",
  important_dates: "Important dates",
  preferences: "Preferences",
  relationships: "Relationships",
  routines: "Routines",
  goals: "Goals",
  constraints: "Constraints",
  other: "Other",
}

const SOURCE_LABELS: Record<string, string> = {
  explicit_user_statement: "You said this clearly",
  user_answer_in_context: "Learned from your answer",
  user_correction: "Corrected by you",
  repeated_pattern: "Repeated pattern",
  assistant_confirmation: "Confirmed in chat",
  manual_review: "Added manually",
}

function humanizeLabel(value?: string | null) {
  if (!value) return "—"
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

function categoryLabel(value?: string | null) {
  return CATEGORY_LABELS[value || ""] || humanizeLabel(value)
}

function sourceLabel(value?: string | null) {
  return SOURCE_LABELS[value || ""] || humanizeLabel(value)
}

function strengthLabel(value?: number | null) {
  if (value == null) return "Unknown"
  if (value >= 0.9) return "Very strong"
  if (value >= 0.75) return "Strong"
  if (value >= 0.55) return "Medium"
  return "Low"
}

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
  const assistantName = useAssistantDisplayName();
  const memoriesEyebrow = useAssistantOwnedLabel("Memories");
  const [data, setData] = useState<MemoryReviewPayload | null>(null)
  const [quality, setQuality] = useState<MemoryQualityPayload | null>(null)
  const [memoryHealthStatus, setMemoryHealthStatus] = useState<MemoryHealthSchedulerStatus | null>(null)
  const [calendarCandidates, setCalendarCandidates] = useState<CalendarCandidatesPayload | null>(null)
  const [loading, setLoading] = useState(true)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [consolidating, setConsolidating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<"active" | "archived" | "review" | "calendar">("active")
  const [query, setQuery] = useState("")
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({})
  const [edit, setEdit] = useState<EditState | null>(null)
  const [manualAddOpen, setManualAddOpen] = useState(false)
  const [manualContent, setManualContent] = useState("")
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
      await loadQuality()
      await loadMemoryHealthStatus()
      await loadCalendarCandidates()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories")
    } finally {
      setLoading(false)
    }
  }

  async function loadQuality() {
    try {
      const res = await fetch("/api/memory-review/quality", {
        cache: "no-store",
      })

      if (!res.ok) return

      setQuality((await res.json()) as MemoryQualityPayload)
    } catch {
      setQuality(null)
    }
  }

  async function loadMemoryHealthStatus() {
    try {
      const schedulerRes = await fetch("/api/memory-review/quality/scheduler/status", {
        cache: "no-store",
      })

      if (schedulerRes.ok) {
        const schedulerJson = (await schedulerRes.json()) as MemoryHealthSchedulerStatus

        if (typeof schedulerJson.user_summary?.needs_review === "number") {
          setMemoryHealthStatus({
            ...schedulerJson,
            health_source: "scheduler",
          })
          return
        }
      }

      const liveRes = await fetch("/api/memory-review/quality", {
        cache: "no-store",
      })

      if (!liveRes.ok) {
        setMemoryHealthStatus(null)
        return
      }

      const liveJson = (await liveRes.json()) as MemoryQualityPayload
      setMemoryHealthStatus({
        health_source: "live",
        user_summary: {
          needs_review: liveJson.summary.needs_review,
          duplicate_groups: liveJson.summary.duplicate_groups,
          conflict_groups: liveJson.summary.conflict_groups,
          low_quality_memories: liveJson.summary.low_quality_memories,
          stale_memories: liveJson.summary.stale_memories || 0,
        },
      })
    } catch {
      setMemoryHealthStatus(null)
    }
  }


  async function loadCalendarCandidates() {
    try {
      const res = await fetch("/api/memory-review/calendar-candidates", {
        cache: "no-store",
      })

      if (!res.ok) {
        setCalendarCandidates(null)
        return
      }

      setCalendarCandidates((await res.json()) as CalendarCandidatesPayload)
    } catch {
      setCalendarCandidates(null)
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
    void loadMemoryHealthStatus()
    void loadCalendarCandidates()
  }, [])

  const currentGroups = tab === "review" || tab === "calendar" ? {} : data?.[tab] || {}

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
          "Memory actions can add, edit, archive, restore, or summarize long-term memories. Please create a 6-digit Memory PIN first in Settings.",
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
      "Summarize patterns",
      `${assistantName} will turn repeated memory patterns into a clearer long-term summary.`,
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
          pin,
        }),
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || "Failed to add memory")
      }

      setManualContent("")
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

  async function resolveQualityIssue({
    actionName,
    keepMemoryId,
    archiveMemoryIds,
    pin,
  }: {
    actionName: "keep_one_archive_rest" | "archive_memory"
    keepMemoryId?: string | null
    archiveMemoryIds: string[]
    pin: string
  }) {
    setSavingId("quality-resolve")
    setError(null)

    try {
      const res = await fetch("/api/memory-review/quality/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action: actionName,
          keep_memory_id: keepMemoryId || null,
          archive_memory_ids: archiveMemoryIds,
          pin,
        }),
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || "Failed to resolve memory issue")
      }

      await load()
      await loadQuality()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve memory issue")
    } finally {
      setSavingId(null)
    }
  }

  async function calendarCandidateAction(
    candidate: CalendarCandidateItem,
    actionName: "dismiss" | "archive" | "confirm-local" | "sync-google",
    pin: string,
  ) {
    setSavingId(`calendar-${candidate.id}`)
    setError(null)

    try {
      const res = await fetch(`/api/memory-review/calendar-candidates/${candidate.id}/${actionName}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || "Failed to update calendar candidate")
      }

      await load()
      await loadCalendarCandidates()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update calendar candidate")
    } finally {
      setSavingId(null)
    }
  }

  async function confirmMemoryFreshness(memoryId: string) {
    setSavingId(memoryId)
    setError(null)

    try {
      const res = await fetch(`/api/memory-review/${memoryId}/confirm`, {
        method: "POST",
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || "Failed to confirm memory")
      }

      await load()
      await loadQuality()
      await loadMemoryHealthStatus()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to confirm memory")
    } finally {
      setSavingId(null)
    }
  }

  const activeCount = data?.counts?.active ?? 0
  const archivedCount = data?.counts?.archived ?? 0
  const reviewCount = quality?.summary?.needs_review ?? 0
  const calendarCandidateCount = calendarCandidates?.count ?? 0

  return (
    <main className="min-h-screen px-4 py-6 text-slate-950 dark:text-slate-900 dark:text-zinc-100 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="rounded-[2rem] border border-slate-200/70 bg-white/75 p-6 shadow-2xl shadow-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.04] dark:shadow-black/30">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.28em] text-cyan-700 dark:text-cyan-300/80">
                {memoriesEyebrow}
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-4xl">
                Memories
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700 dark:text-zinc-300">
                Review what {assistantName} remembers, manage active memories, and
                inspect archived or archived memories in one place.
              </p>
            </div>

            <div className="flex flex-wrap gap-3">
              <BackToLastChat className="inline-flex h-10 items-center justify-center rounded-full border border-border bg-fg/[0.035] px-4 text-sm font-medium text-fg-muted shadow-sm transition hover:bg-fg/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 active:scale-[0.98]">
                Back to chat
              </BackToLastChat>
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
                  Summarize patterns
                </button>

                <div
                  id="consolidate-tooltip"
                  role="tooltip"
                  className="pointer-events-none absolute right-0 top-full z-30 mt-2 w-64 rounded-2xl border border-slate-200/70 bg-white/95 px-3 py-2 text-xs leading-5 text-slate-600 opacity-0 shadow-xl shadow-slate-900/10 backdrop-blur-xl transition group-hover:opacity-100 dark:border-white/10 dark:bg-zinc-950/95 dark:text-zinc-300"
                >
                  Creates a clearer summary from repeated memory patterns.
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

          <div className="mt-6 grid gap-3 sm:grid-cols-5">
            <StatCard label="Active" value={activeCount} />
            <StatCard label="Archived" value={archivedCount} />
            <StatCard label="Needs Review" value={reviewCount} />
            <StatCard label="Calendar" value={calendarCandidateCount} />
            <StatCard label="Total" value={data?.counts?.total ?? 0} />
          </div>

          {reviewCount > 0 ? (
            <div className="mt-4 rounded-2xl border border-amber-200/70 bg-amber-50/80 p-4 text-sm leading-6 text-amber-900 shadow-sm shadow-amber-900/5 dark:border-amber-300/15 dark:bg-amber-300/10 dark:text-amber-100">
              Memory review found {reviewCount} memor
              {reviewCount === 1 ? "y" : "ies"} that may need review.
              Open the Needs Review tab to inspect and resolve them.
            </div>
          ) : null}
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
              label={`Archived (${archivedCount})`}
            />
            <TabButton
              active={tab === "review"}
              onClick={() => setTab("review")}
              label={`Needs Review (${reviewCount})`}
            />
            <TabButton
              active={tab === "calendar"}
              onClick={() => setTab("calendar")}
              label={`Calendar (${calendarCandidateCount})`}
            />
          </div>

          <div className="relative w-full md:max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-zinc-500" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search memories..."
              className="w-full rounded-full border border-slate-200/70 dark:border-white/10 bg-white/80 dark:bg-black/25 py-2 pl-10 pr-4 text-sm text-slate-950 dark:text-white outline-none placeholder:text-slate-500 dark:text-zinc-500 focus:border-cyan-300/70"
            />
          </div>
        </section>

        {error ? (
          <div className="rounded-2xl border border-red-400/40 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-100">
            {error}
          </div>
        ) : null}

        {tab === "calendar" ? (
          <CalendarCandidatePanel
            candidates={calendarCandidates?.items || []}
            loading={loading}
            savingId={savingId}
            onSyncGoogle={(candidate) =>
              requireMemoryPin(
                "Create Google Calendar event",
                "This will create a real all-day event in your connected Google Calendar.",
                async (pin) => {
                  await calendarCandidateAction(candidate, "sync-google", pin)
                },
              )
            }
            onConfirmLocal={(candidate) =>
              requireMemoryPin(
                "Confirm event draft",
                "This creates a local calendar event draft. It will not create a Google Calendar event yet.",
                async (pin) => {
                  await calendarCandidateAction(candidate, "confirm-local", pin)
                },
              )
            }
            onDismiss={(candidate) =>
              requireMemoryPin(
                "Remove calendar candidate",
                "This keeps the memory, but removes it from the Calendar Candidates tab.",
                async (pin) => {
                  await calendarCandidateAction(candidate, "dismiss", pin)
                },
              )
            }
            onArchive={(candidate) =>
              requireMemoryPin(
                "Archive calendar candidate",
                "This archives the selected memory-backed calendar candidate.",
                async (pin) => {
                  await calendarCandidateAction(candidate, "archive", pin)
                },
              )
            }
          />
        ) : tab === "review" ? (
          <MemoryQualityPanel
            quality={quality}
            loading={loading}
            saving={savingId === "quality-resolve"}
            onConfirmMemory={(memoryId) => void confirmMemoryFreshness(memoryId)}
            onResolve={(params) =>
              requireMemoryPin(
                "Resolve memory issue",
                "Enter your 6-digit Memory PIN before changing memory status.",
                async (pin) => {
                  await resolveQualityIssue({ ...params, pin })
                },
              )
            }
          />
        ) : loading ? (
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
          onContentChange={setManualContent}
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

function CalendarCandidatePanel({
  candidates,
  loading,
  savingId,
  onSyncGoogle,
  onConfirmLocal,
  onDismiss,
  onArchive,
}: {
  candidates: CalendarCandidateItem[]
  loading: boolean
  savingId: string | null
  onSyncGoogle: (candidate: CalendarCandidateItem) => void
  onConfirmLocal: (candidate: CalendarCandidateItem) => void
  onDismiss: (candidate: CalendarCandidateItem) => void
  onArchive: (candidate: CalendarCandidateItem) => void
}) {
  if (loading) return <LoadingState />

  if (!candidates.length) {
    return (
      <div className="rounded-[1.5rem] border border-emerald-200/70 bg-emerald-50/70 p-8 text-center shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-emerald-300/15 dark:bg-emerald-300/10">
        <CalendarDays className="mx-auto h-8 w-8 text-emerald-600 dark:text-emerald-300" />
        <h2 className="mt-3 text-lg font-semibold text-slate-950 dark:text-white">
          No calendar candidates
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600 dark:text-zinc-300">
          Time-bound memories that may belong on your calendar will appear here for review.
        </p>
      </div>
    )
  }

  return (
    <section className="space-y-4">
      <div className="overflow-hidden rounded-[1.5rem] border border-slate-200/70 bg-white/70 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]">
        <div className="border-b border-slate-200/70 p-5 dark:border-white/10">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-cyan-400/15 p-2 text-cyan-700 dark:text-cyan-300">
              <CalendarDays className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                Calendar candidates
              </h2>
              <p className="text-sm text-slate-500 dark:text-zinc-400">
                Review time-bound memories before turning them into calendar events.
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 p-4 lg:grid-cols-2">
          {candidates.map((candidate) => {
            const saving = savingId === `calendar-${candidate.id}`

            return (
              <div
                key={candidate.id}
                className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-black/20"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-xs uppercase tracking-[0.18em] text-cyan-700 dark:text-cyan-300/80">
                      Calendar candidate
                    </p>
                    <h3 className="mt-2 text-base font-semibold leading-6 text-slate-950 dark:text-white">
                      {candidate.structured_value || candidate.content || "Untitled candidate"}
                    </h3>
                  </div>
                  <span className="rounded-full bg-cyan-400/15 px-3 py-1 text-xs font-medium text-cyan-800 dark:text-cyan-200">
                    {candidate.due_date || "No date"}
                  </span>
                </div>

                {candidate.content ? (
                  <p className="mt-3 text-sm leading-6 text-slate-600 dark:text-zinc-300">
                    {candidate.content}
                  </p>
                ) : null}

                <div className="mt-4 grid gap-2 text-xs text-slate-500 dark:text-zinc-400 sm:grid-cols-2">
                  <div>
                    <span className="font-medium text-slate-700 dark:text-zinc-200">Due date:</span>{" "}
                    {candidate.due_date || "—"}
                  </div>
                  <div>
                    <span className="font-medium text-slate-700 dark:text-zinc-200">Expires:</span>{" "}
                    {formatDateTime(candidate.expires_at)}
                  </div>
                  <div>
                    <span className="font-medium text-slate-700 dark:text-zinc-200">Field:</span>{" "}
                    {humanizeLabel(candidate.structured_field)}
                  </div>
                  <div>
                    <span className="font-medium text-slate-700 dark:text-zinc-200">Created:</span>{" "}
                    {formatDateTime(candidate.created_at)}
                  </div>
                  <div>
                    <span className="font-medium text-slate-700 dark:text-zinc-200">Event status:</span>{" "}
                    {humanizeLabel(candidate.calendar_event_status) || "Candidate"}
                  </div>
                  <div>
                    <span className="font-medium text-slate-700 dark:text-zinc-200">Synced:</span>{" "}
                    {formatDateTime(candidate.calendar_synced_at)}
                  </div>
                </div>

                {candidate.calendar_sync_error ? (
                  <p className="mt-3 rounded-2xl border border-red-200/70 bg-red-50/80 px-3 py-2 text-xs leading-5 text-red-700 dark:border-red-300/15 dark:bg-red-500/10 dark:text-red-200">
                    {candidate.calendar_sync_error}
                  </p>
                ) : null}

                {candidate.google_calendar_event_link ? (
                  <a
                    href={candidate.google_calendar_event_link}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-3 inline-flex items-center gap-2 rounded-full border border-emerald-200/70 bg-emerald-50/80 px-3 py-2 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 dark:border-emerald-300/15 dark:bg-emerald-500/10 dark:text-emerald-200"
                  >
                    <ExternalLink className="h-3.5 w-3.5" />
                    Open in Google Calendar
                  </a>
                ) : null}

                <div className="mt-4 flex flex-wrap gap-2">
                  {candidate.calendar_event_status === "confirmed_local" ? (
                    <button
                      onClick={() => onSyncGoogle(candidate)}
                      disabled={saving || !candidate.calendar_event_date}
                      className="inline-flex items-center gap-2 rounded-full bg-emerald-400 px-3 py-2 text-xs font-medium text-zinc-950 transition hover:bg-emerald-300 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CalendarDays className="h-3.5 w-3.5" />}
                      Create Google Calendar event
                    </button>
                  ) : candidate.calendar_event_status === "synced_google" ? null : (
                    <button
                      onClick={() => onConfirmLocal(candidate)}
                      disabled={saving || !candidate.due_date}
                      className="inline-flex items-center gap-2 rounded-full bg-cyan-400 px-3 py-2 text-xs font-medium text-zinc-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
                    >
                      {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ClipboardCheck className="h-3.5 w-3.5" />}
                      Confirm event draft
                    </button>
                  )}
                  <button
                    onClick={() => onDismiss(candidate)}
                    disabled={saving}
                    className="inline-flex items-center gap-2 rounded-full border border-slate-200/70 bg-white/70 px-3 py-2 text-xs font-medium text-slate-700 transition hover:bg-white disabled:opacity-60 dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-200 dark:hover:bg-white/10"
                  >
                    {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <X className="h-3.5 w-3.5" />}
                    Not calendar event
                  </button>
                  <button
                    onClick={() => onArchive(candidate)}
                    disabled={saving}
                    className="inline-flex items-center gap-2 rounded-full border border-red-200/70 bg-red-50/80 px-3 py-2 text-xs font-medium text-red-700 transition hover:bg-red-100 disabled:opacity-60 dark:border-red-300/15 dark:bg-red-500/10 dark:text-red-200"
                  >
                    {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Archive className="h-3.5 w-3.5" />}
                    Archive
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}

function formatDateTime(value?: string | null) {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

function MemoryQualityPanel({
  quality,
  loading,
  saving,
  onResolve,
  onConfirmMemory,
}: {
  quality: MemoryQualityPayload | null
  loading: boolean
  saving: boolean
  onResolve: (params: {
    actionName: "keep_one_archive_rest" | "archive_memory"
    keepMemoryId?: string | null
    archiveMemoryIds: string[]
  }) => void
  onConfirmMemory: (memoryId: string) => void
}) {
  if (loading) return <LoadingState />

  const items = quality?.review_items || []

  if (!quality || items.length === 0) {
    return (
      <div className="rounded-[1.5rem] border border-emerald-200/70 bg-emerald-50/70 p-8 text-center shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-emerald-300/15 dark:bg-emerald-300/10">
        <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-600 dark:text-emerald-300" />
        <h2 className="mt-3 text-lg font-semibold text-slate-950 dark:text-white">
          No memory issues found
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600 dark:text-zinc-300">
          The assistant did not find obvious duplicates, conflicts, or unclear memories.
        </p>
      </div>
    )
  }

  return (
    <section className="space-y-4">
      <div className="grid gap-3 md:grid-cols-3">
        <StatCard label="Possible Duplicates" value={quality.summary.duplicate_groups} />
        <StatCard label="Possible Conflicts" value={quality.summary.conflict_groups} />
        <StatCard label="Needs More Detail" value={quality.summary.low_quality_memories} />
        <StatCard label="Needs Confirmation" value={quality.summary.stale_memories || 0} />
      </div>

      <div className="overflow-hidden rounded-[1.5rem] border border-slate-200/70 bg-white/70 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]">
        <div className="border-b border-slate-200/70 p-5 dark:border-white/10">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-amber-400/15 p-2 text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                Memories that may need review
              </h2>
              <p className="text-sm text-slate-500 dark:text-zinc-400">
                These are read-only suggestions. Use Edit, Forget, or Restore from the Active/Archived tabs.
              </p>
            </div>
          </div>
        </div>

        <div className="grid gap-3 p-4">
          {items.map((item, index) => (
            <MemoryQualityIssueCard
              key={`${item.issue_type}-${index}`}
              item={item}
              saving={saving}
              onResolve={onResolve}
              onConfirmMemory={onConfirmMemory}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

function MemoryQualityReasonBox({
  reason,
}: {
  reason?: MemoryQualityReasonInfo | null
}) {
  if (!reason) return null

  const values = reason.values?.filter(Boolean) || []
  const reasons = reason.reasons?.filter(Boolean) || []

  return (
    <div className="mt-3 rounded-2xl border border-cyan-200/70 bg-cyan-50/70 p-3 text-sm leading-6 text-cyan-950 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
      <p className="font-medium">Why this is flagged</p>

      {reason.main ? <p className="mt-1">{reason.main}</p> : null}

      {reason.field ? (
        <p className="mt-2 text-xs text-cyan-800/80 dark:text-cyan-100/75">
          Memory detail: {humanizeLabel(reason.field)}
        </p>
      ) : null}

      {values.length ? (
        <div className="mt-2">
          <p className="text-xs text-cyan-800/80 dark:text-cyan-100/75">
            Stored value{values.length === 1 ? "" : "s"}:
          </p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {values.map((value) => (
              <li key={value}>{value}</li>
            ))}
          </ul>
        </div>
      ) : null}

      {reasons.length ? (
        <div className="mt-2">
          <p className="text-xs text-cyan-800/80 dark:text-cyan-100/75">
            Specific reason{reasons.length === 1 ? "" : "s"}:
          </p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {reasons.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}

function MemoryQualityIssueCard({
  item,
  saving,
  onResolve,
  onConfirmMemory,
}: {
  item: MemoryQualityReviewItem
  saving: boolean
  onResolve: (params: {
    actionName: "keep_one_archive_rest" | "archive_memory"
    keepMemoryId?: string | null
    archiveMemoryIds: string[]
  }) => void
  onConfirmMemory: (memoryId: string) => void
}) {
  const severityClass =
    item.severity === "high"
      ? "border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-200"
      : item.severity === "medium"
        ? "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-400/20 dark:bg-amber-500/10 dark:text-amber-200"
        : "border-slate-200 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-200"

  const memories: MemoryQualityReviewMemory[] =
    item.memories?.length
      ? item.memories
      : item.memory_ids.map((id) => ({
          id,
          content: `Memory ${id}`,
          category: null,
          structured_field: null,
          structured_value: null,
        }))

  const canKeepOne =
    (item.issue_type === "duplicate" || item.issue_type === "conflict") &&
    memories.length > 1

  const canConfirmStale =
    item.issue_type === "stale_memory" &&
    memories.length === 1

  const canArchiveSingle =
    (item.issue_type === "low_quality" || item.issue_type === "stale_memory") &&
    memories.length === 1

  return (
    <article className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-black/20">
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${severityClass}`}>
                {humanizeLabel(item.severity)}
              </span>
              <span className="rounded-full border border-slate-200/70 px-2.5 py-1 text-xs text-slate-500 dark:border-white/10 dark:text-zinc-400">
                {humanizeLabel(item.issue_type)}
              </span>
            </div>

            <h3 className="mt-3 text-base font-semibold text-slate-950 dark:text-white">
              {item.title}
            </h3>
            <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-300">
              {item.explanation}
            </p>
            <p className="mt-2 text-sm leading-6 text-slate-500 dark:text-zinc-400">
              Suggested action: {item.suggested_action}
            </p>

          <MemoryQualityReasonBox reason={item.reason} />
          </div>

          <div className="shrink-0 rounded-xl bg-slate-100 px-3 py-2 text-xs text-slate-500 dark:bg-white/[0.06] dark:text-zinc-400">
            {memories.length} memor{memories.length === 1 ? "y" : "ies"}
          </div>
        </div>

        <div className="grid gap-3">
          {memories.map((memory, index) => {
            const archiveMemoryIds = memories
              .map((item) => item.id)
              .filter((id) => id !== memory.id)

            return (
              <div
                key={memory.id}
                className="rounded-2xl border border-slate-200/70 bg-slate-50/80 p-3 dark:border-white/10 dark:bg-white/[0.04]"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
                      Memory {index + 1}
                    </p>
                    <p className="mt-2 text-sm leading-6 text-slate-800 dark:text-zinc-100">
                      {memory.content}
                    </p>

                    <div className="mt-3 flex flex-wrap gap-2">
                      {memory.category ? <Badge>{categoryLabel(memory.category)}</Badge> : null}
                      {memory.structured_field ? <Badge>{humanizeLabel(memory.structured_field)}</Badge> : null}
                      {memory.structured_value ? <Badge>{memory.structured_value}</Badge> : null}
                    </div>
                  </div>

                  {canKeepOne ? (
                    <button
                      onClick={() =>
                        onResolve({
                          actionName: "keep_one_archive_rest",
                          keepMemoryId: memory.id,
                          archiveMemoryIds,
                        })
                      }
                      disabled={saving}
                      className="shrink-0 rounded-full border border-slate-200/70 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-white/[0.04] dark:text-zinc-200 dark:hover:bg-white/10"
                    >
                      Keep this, archive others
                    </button>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>

        {canConfirmStale ? (
          <div>
            <button
              onClick={() => onConfirmMemory(memories[0].id)}
              disabled={saving}
              className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-medium text-emerald-700 transition hover:bg-emerald-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-400/20 dark:bg-emerald-500/10 dark:text-emerald-200 dark:hover:bg-emerald-500/20"
            >
              Still true
            </button>
          </div>
        ) : null}

        {canArchiveSingle ? (
          <div>
            <button
              onClick={() =>
                onResolve({
                  actionName: "archive_memory",
                  archiveMemoryIds: memories.map((memory) => memory.id),
                })
              }
              disabled={saving}
              className="rounded-full border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-200 dark:hover:bg-red-500/20"
            >
              Archive this memory
            </button>
          </div>
        ) : null}
      </div>
    </article>
  )
}


function formatDate(value?: string | null) {
  if (!value) return "—"

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value

  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
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
  tab: "active" | "archived" | "review"
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
          {memory.source_priority ? <Badge>{sourceLabel(memory.source_priority)}</Badge> : null}
          {memory.archived ? <Badge tone="archived">archived</Badge> : null}
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


function LoadingState() {
  return (
    <div className="rounded-[1.5rem] border border-slate-200/70 bg-white/70 p-6 shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]">
      <div className="space-y-4">
        <div className="h-5 w-40 animate-pulse rounded-full bg-slate-200 dark:bg-white/10" />
        <div className="grid gap-4 md:grid-cols-2">
          <div className="h-36 animate-pulse rounded-2xl bg-slate-100 dark:bg-white/5" />
          <div className="h-36 animate-pulse rounded-2xl bg-slate-100 dark:bg-white/5" />
        </div>
      </div>
    </div>
  )
}

function EmptyState({
  tab,
  query,
}: {
  tab: "active" | "archived"
  query: string
}) {
  const hasSearch = query.trim().length > 0

  return (
    <div className="rounded-[1.5rem] border border-slate-200/70 bg-white/70 p-8 text-center shadow-xl shadow-slate-900/5 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]">
      <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
        {hasSearch ? "No matching memories" : "No memories found"}
      </h2>
      <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-500 dark:text-zinc-400">
        {hasSearch
          ? "Try a different search term."
          : tab === "archived"
            ? "Archived memories will appear here after you forget or replace an existing memory."
            : "The assistant has no active memories yet. Add one, or keep chatting so the assistant can learn what matters."}
      </p>
    </div>
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
            onKeyDown={(event) => {
              if (event.key === "Enter" && pin.length === 6 && !saving) {
                event.preventDefault()
                onConfirm()
              }
            }}
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
  onContentChange,
  onCancel,
  onSave,
}: {
  saving: boolean
  content: string
  onContentChange: (value: string) => void
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
              Write what the assistant should remember. The assistant will organize it automatically.
            </p>
          </div>
          <button
            onClick={onCancel}
            className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
            aria-label="Close add memory"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-sm text-slate-700 dark:text-zinc-300">
              What should the assistant remember?
            </span>
            <textarea
              value={content}
              onChange={(event) => onContentChange(event.target.value)}
              rows={6}
              placeholder="Example: I prefer careful, complete code fixes instead of quick incremental patches."
              className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
            />
          </label>

          <div className="rounded-2xl border border-cyan-200/70 bg-cyan-50/70 p-3 text-xs leading-5 text-cyan-900 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
            The assistant will automatically decide the memory type and details in the background.
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
  saving,
  edit,
  onChange,
  onCancel,
  onSave,
}: {
  saving: boolean
  edit: EditState
  onChange: (edit: EditState) => void
  onCancel: () => void
  onSave: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4 backdrop-blur-sm dark:bg-black/70">
      <div className="w-full max-w-2xl rounded-[1.5rem] border border-slate-200/70 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-[#10101c]">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-950 dark:text-white">
              Edit memory
            </h2>
            <p className="mt-1 text-sm text-slate-500 dark:text-zinc-400">
              Update what the assistant should remember. The assistant will organize it automatically.
            </p>
          </div>
          <button
            onClick={onCancel}
            className="rounded-full p-2 text-slate-500 hover:bg-slate-100 hover:text-slate-950 dark:text-zinc-400 dark:hover:bg-white/10 dark:hover:text-white"
            aria-label="Close edit memory"
          >
            <X className="h-5 w-5" />
          </button>
        </div>

        <div className="mt-5 space-y-4">
          <label className="block">
            <span className="text-sm text-slate-700 dark:text-zinc-300">
              What should the assistant remember?
            </span>
            <textarea
              value={edit.content}
              onChange={(event) => onChange({ ...edit, content: event.target.value })}
              rows={6}
              placeholder="Example: I prefer careful, complete code fixes instead of quick incremental patches."
              className="mt-2 w-full rounded-2xl border border-slate-200/70 bg-white/80 p-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
            />
          </label>

          <div className="rounded-2xl border border-cyan-200/70 bg-cyan-50/70 p-3 text-xs leading-5 text-cyan-900 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
            The assistant will automatically update the memory type and details in the background.
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
            disabled={saving || edit.content.trim().length < 3}
            className="inline-flex items-center justify-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-slate-950 hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
            Save changes
          </button>
        </div>
      </div>
    </div>
  )
}

async function safeDetail(res: Response) {
  try {
    const json = await res.json()
    return json?.detail || json?.message || null
  } catch {
    return null
  }
}
