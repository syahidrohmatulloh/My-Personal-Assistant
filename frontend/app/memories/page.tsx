"use client"

// Calendar has moved to /calendar. Memories no longer exposes Calendar UI.;


import { useEffect, useMemo, useState } from "react"
import type { ReactNode } from "react"
import Link from "next/link"
import {
  Archive,
  AlertTriangle,
  Brain,
  CheckCircle2,
  ClipboardCheck,
  Pencil,
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
import { useAssistantDisplayName } from "@/hooks/use-assistant-display-name";
import { BackToLastChat } from "@/components/navigation/back-to-last-chat";
import { createClient } from "@/lib/supabase/client";
import { readSnapshot, SNAPSHOT_MAX_AGE_MS, userScopedSnapshotKey, writeSnapshot } from "@/lib/snapshot-cache";
import { MemoryNarrativeSummaryPanel, type MemoryNarrativeSummary } from "../../components/memories/memory-narrative-summary-panel";
import { DEFAULT_GRAPH_SECTION_FILTER, MemoryGraphViewPanel, type MemoryGraphSectionFilter, type MemoryGraphViewPayload } from "../../components/memories/memory-graph-view-panel";
import { StatCard, TabButton } from "../../components/memories/memory-page-primitives";
import { MemoryQualityPanel, type MemoryQualityPayload } from "../../components/memories/memory-quality-panel";
import { MemoryCard } from "../../components/memories/memory-card";
import { EditDialog, ManualAddDialog, MemoryPinDialog } from "../../components/memories/memory-dialogs";

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
  last_user_confirmed_at?: string | null
  last_user_confirmation_source?: string | null
  last_user_confirmation_evidence?: Record<string, unknown> | null
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
  assistant_confirmation: "Assistant-originated signal",
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

function memoryWhyItMatters(memory: MemoryItem) {
  const field = (memory.structured_field || "").toLowerCase()
  const category = (memory.category || "").toLowerCase()

  if (field === "assistant_name") {
    return "This affects how your assistant introduces herself and keeps the experience consistent across chats."
  }

  if (field === "name" || field === "nickname") {
    return "This affects how your assistant addresses you naturally across conversations."
  }

  if (field === "timezone" || category === "important_dates") {
    return "This helps your assistant avoid wrong timing, reminders, greetings, and scheduling assumptions."
  }

  if (category === "preferences") {
    return "This helps your assistant personalize suggestions and avoid repeating options that do not fit you."
  }

  if (category === "relationships") {
    return "This helps your assistant understand important people in your life when planning, drafting, or remembering context."
  }

  if (category === "goals") {
    return "This helps your assistant connect future advice to what you are actively trying to achieve."
  }

  if (category === "constraints") {
    return "This helps your assistant avoid suggestions that conflict with your limits, rules, or preferences."
  }

  if (category === "routines") {
    return "This helps your assistant make plans that fit your normal habits and schedule."
  }

  return "This gives your assistant durable context that may improve future answers when it is relevant."
}

function memoryTrustSummary(memory: MemoryItem) {
  const strength = strengthLabel(memory.confidence)
  const source = sourceLabel(memory.source_priority)
  const confirmed = memory.last_user_confirmed_at
    ? `Confirmed ${formatDate(memory.last_user_confirmed_at)}`
    : memory.created_at
      ? `Learned ${formatDate(memory.created_at)}`
      : "No date available"

  return {
    strength,
    source,
    confirmed,
  }
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

type MemoriesSnapshotData = {
  data: MemoryReviewPayload | null
  quality: MemoryQualityPayload | null
  memoryHealthStatus: MemoryHealthSchedulerStatus | null
}

type MemoryInsightCard = {
  key: string
  title: string
  count: number
  description: string
  sample: string[]
  searchQuery?: string
  targetTab?: "active" | "archived" | "review"
}

function flattenMemoryGroups(groups?: Record<string, MemoryItem[]> | null): MemoryItem[] {
  if (!groups) return []
  return Object.values(groups).flat()
}

function memoryCategoryIs(memory: MemoryItem, categories: string[]) {
  const category = String(memory.category || "").toLowerCase()
  const group = String(memory.group || "").toLowerCase()
  return categories.some((item) => category === item || group.includes(item))
}

function memoryHasStructuredField(memory: MemoryItem, fields: string[]) {
  const field = String(memory.structured_field || "").toLowerCase()
  return fields.includes(field)
}

function pickMemorySamples(items: MemoryItem[], limit = 2) {
  return items
    .slice()
    .sort((a, b) => Number(b.confidence || 0) - Number(a.confidence || 0))
    .slice(0, limit)
    .map((item) => item.structured_value || item.content)
    .filter(Boolean)
}

function buildMemoryInsightCards(
  data: MemoryReviewPayload | null,
  quality: MemoryQualityPayload | null,
  memoryHealthStatus: MemoryHealthSchedulerStatus | null,
): MemoryInsightCard[] {
  const active = flattenMemoryGroups(data?.active)
  const identityItems = active.filter(
    (item) =>
      memoryCategoryIs(item, ["identity"]) ||
      memoryHasStructuredField(item, ["name", "nickname", "assistant_name", "timezone", "location"]),
  )
  const preferenceItems = active.filter((item) => memoryCategoryIs(item, ["preferences"]))
  const goalRoutineItems = active.filter((item) =>
    memoryCategoryIs(item, ["goals", "routines"]),
  )
  const relationshipItems = active.filter((item) =>
    memoryCategoryIs(item, ["relationships"]),
  )
  const constraintItems = active.filter((item) =>
    memoryCategoryIs(item, ["constraints"]),
  )

  const needsReview =
    Number(memoryHealthStatus?.user_summary?.needs_review ?? quality?.summary.needs_review ?? 0)

  return [
    {
      key: "identity",
      title: "Identity & profile",
      count: identityItems.length,
      description: "Names, timezone, assistant name, and other facts that keep conversations consistent.",
      sample: pickMemorySamples(identityItems),
      searchQuery: "identity name nickname timezone assistant_name",
      targetTab: "active",
    },
    {
      key: "preferences",
      title: "Preferences",
      count: preferenceItems.length,
      description: "Things your assistant should consider when giving suggestions or making choices for you.",
      sample: pickMemorySamples(preferenceItems),
      searchQuery: "preferences",
      targetTab: "active",
    },
    {
      key: "goals-routines",
      title: "Goals & routines",
      count: goalRoutineItems.length,
      description: "Longer-running goals and repeated habits that should shape planning.",
      sample: pickMemorySamples(goalRoutineItems),
      searchQuery: "goals routines",
      targetTab: "active",
    },
    {
      key: "relationships",
      title: "Important people",
      count: relationshipItems.length,
      description: "People and relationships your assistant may use when helping with personal context.",
      sample: pickMemorySamples(relationshipItems),
      searchQuery: "relationships",
      targetTab: "active",
    },
    {
      key: "constraints",
      title: "Constraints",
      count: constraintItems.length,
      description: "Limits, rules, and things to avoid when your assistant gives recommendations.",
      sample: pickMemorySamples(constraintItems),
      searchQuery: "constraints",
      targetTab: "active",
    },
    {
      key: "needs-review",
      title: "To look over",
      count: needsReview,
      description: "Potential duplicates, conflicts, stale memories, or unclear memories waiting for cleanup.",
      sample:
        needsReview > 0
          ? [`${needsReview} item${needsReview === 1 ? "" : "s"} need review`]
          : ["No urgent memory cleanup needed"],
      targetTab: "review",
    },
  ]
}

const LEGACY_MEMORIES_SNAPSHOT_KEY = "app:memories-snapshot:v1"
const MEMORIES_SNAPSHOT_AREA = "memories"

function memoriesSnapshotKeyForUser(userId: string): string {
  return userScopedSnapshotKey({
    userId,
    area: MEMORIES_SNAPSHOT_AREA,
  })
}

function isMemoriesSnapshotData(value: unknown): value is MemoriesSnapshotData {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function readMemoriesSnapshot(
  key = LEGACY_MEMORIES_SNAPSHOT_KEY,
): MemoriesSnapshotData | null {
  const snapshot = readSnapshot<MemoriesSnapshotData>(
    key,
    {
      data: null,
      quality: null,
      memoryHealthStatus: null,
    },
    isMemoriesSnapshotData,
    { maxAgeMs: SNAPSHOT_MAX_AGE_MS.memories },
  )

  return snapshot?.data ?? null
}

function writeMemoriesSnapshot(
  payload: MemoriesSnapshotData,
  key = LEGACY_MEMORIES_SNAPSHOT_KEY,
) {
  writeSnapshot(key, payload)
}

export default function MemoriesPage() {
  const assistantName = useAssistantDisplayName();
  const memoriesEyebrow = useAssistantOwnedLabel("Memories");
  const initialSnapshot = useMemo(() => readMemoriesSnapshot(), [])
  const [snapshotKey, setSnapshotKey] = useState(LEGACY_MEMORIES_SNAPSHOT_KEY)
  const [data, setData] = useState<MemoryReviewPayload | null>(initialSnapshot?.data ?? null)
  const [quality, setQuality] = useState<MemoryQualityPayload | null>(initialSnapshot?.quality ?? null)
  const [memoryHealthStatus, setMemoryHealthStatus] = useState<MemoryHealthSchedulerStatus | null>(initialSnapshot?.memoryHealthStatus ?? null)
  const [loading, setLoading] = useState(() => !initialSnapshot?.data)
  const [savingId, setSavingId] = useState<string | null>(null)
  const [consolidating, setConsolidating] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [tab, setTab] = useState<"active" | "archived" | "review" | "graph">("active")
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
  const [memoryPinSessionNotice, setMemoryPinSessionNotice] = useState<string | null>(null)
  const [resolvedQualityIssueKeys, setResolvedQualityIssueKeys] = useState<Record<string, boolean>>({})
  const [memoryActionNotice, setMemoryActionNotice] = useState<string | null>(null)
  const [narrativeSummary, setNarrativeSummary] = useState<MemoryNarrativeSummary | null>(null)
  const [narrativeLoading, setNarrativeLoading] = useState(false)
  const [narrativeRegenerating, setNarrativeRegenerating] = useState(false)
  const [graphView, setGraphView] = useState<MemoryGraphViewPayload | null>(null)
  const [graphLoading, setGraphLoading] = useState(false)
  const [graphSectionFilter, setGraphSectionFilter] = useState<MemoryGraphSectionFilter>(DEFAULT_GRAPH_SECTION_FILTER)
  const [showGraphDetails, setShowGraphDetails] = useState(false)

  async function loadMemoryNarrativeSummary() {
    setNarrativeLoading(true)

    try {
      const res = await fetch("/api/memory-review/summary", {
        cache: "no-store",
      })

      if (!res.ok) return

      setNarrativeSummary((await res.json()) as MemoryNarrativeSummary)
    } catch {
      setNarrativeSummary(null)
    } finally {
      setNarrativeLoading(false)
    }
  }

  async function regenerateMemoryNarrativeSummary() {
    setNarrativeRegenerating(true)
    setError(null)

    try {
      const res = await fetch("/api/memory-review/summary/regenerate", {
        method: "POST",
        cache: "no-store",
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || "Failed to regenerate memory summary")
      }

      setNarrativeSummary((await res.json()) as MemoryNarrativeSummary)
      setMemoryActionNotice(`${assistantName} refreshed her narrative understanding of you.`)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to regenerate memory summary")
    } finally {
      setNarrativeRegenerating(false)
    }
  }

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

      const [nextQuality, nextHealthStatus] = await Promise.all([
        loadQuality(),
        loadMemoryHealthStatus(),
      ])

      writeMemoriesSnapshot(
        {
          data: json,
          quality: nextQuality,
          memoryHealthStatus: nextHealthStatus,
        },
        snapshotKey,
      )

      void loadMemoryNarrativeSummary()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories")
    } finally {
      setLoading(false)
    }
  }

  async function loadQuality(): Promise<MemoryQualityPayload | null> {
    try {
      const res = await fetch("/api/memory-review/quality", {
        cache: "no-store",
      })

      if (!res.ok) return null

      const payload = (await res.json()) as MemoryQualityPayload
      setQuality(payload)
      return payload
    } catch {
      setQuality(null)
      return null
    }
  }

  async function loadMemoryHealthStatus(): Promise<MemoryHealthSchedulerStatus | null> {
    try {
      const schedulerRes = await fetch("/api/memory-review/quality/scheduler/status", {
        cache: "no-store",
      })

      if (schedulerRes.ok) {
        const schedulerJson = (await schedulerRes.json()) as MemoryHealthSchedulerStatus

        if (typeof schedulerJson.user_summary?.needs_review === "number") {
          const payload: MemoryHealthSchedulerStatus = {
            ...schedulerJson,
            health_source: "scheduler",
          }
          setMemoryHealthStatus(payload)
          return payload
        }
      }

      const liveRes = await fetch("/api/memory-review/quality", {
        cache: "no-store",
      })

      if (!liveRes.ok) {
        setMemoryHealthStatus(null)
        return null
      }

      const liveJson = (await liveRes.json()) as MemoryQualityPayload
      const payload: MemoryHealthSchedulerStatus = {
        health_source: "live",
        user_summary: {
          needs_review: liveJson.summary.needs_review,
          duplicate_groups: liveJson.summary.duplicate_groups,
          conflict_groups: liveJson.summary.conflict_groups,
          low_quality_memories: liveJson.summary.low_quality_memories,
          stale_memories: liveJson.summary.stale_memories || 0,
        },
      }
      setMemoryHealthStatus(payload)
      return payload
    } catch {
      setMemoryHealthStatus(null)
      return null
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



  async function loadMemoryGraphView(pin?: string) {
    const activePin = pin || verifiedMemoryPin

    if (!activePin) {
      requireMemoryPin(
        "Unlock memory graph",
        "Enter your 6-digit Memory PIN before viewing the read-only memory graph.",
        async (nextPin) => {
          await loadMemoryGraphView(nextPin)
        },
      )
      return
    }

    setGraphLoading(true)
    setError(null)
    try {
      const res = await fetch("/api/memory-review/graph-view", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin: activePin }),
        cache: "no-store",
      })

      if (!res.ok) {
        const detail = await safeDetail(res)
        throw new Error(detail || `Failed to load memory graph (${res.status})`)
      }

      setGraphView((await res.json()) as MemoryGraphViewPayload)
    } catch (err) {
      setGraphView(null)
      clearVerifiedMemoryPinSession()
      setError(err instanceof Error ? err.message : "Failed to load memory graph")
    } finally {
      setGraphLoading(false)
    }
  }

  useEffect(() => {
    let cancelled = false

    async function resolveUserScopedSnapshotKey() {
      const supabase = createClient()
      const {
        data: { session },
      } = await supabase.auth.getSession()

      if (cancelled) return

      const userId = session?.user?.id
      if (!userId) return

      const scopedKey = memoriesSnapshotKeyForUser(userId)
      const scopedSnapshot = readMemoriesSnapshot(scopedKey)

      if (scopedSnapshot) {
        setData(scopedSnapshot.data)
        setQuality(scopedSnapshot.quality)
        setMemoryHealthStatus(scopedSnapshot.memoryHealthStatus)
      } else if (data) {
        writeMemoriesSnapshot(
          {
            data,
            quality,
            memoryHealthStatus,
          },
          scopedKey,
        )
      }

      setSnapshotKey(scopedKey)
    }

    void resolveUserScopedSnapshotKey()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    void load()
  }, [snapshotKey])

  useEffect(() => {
    void loadPinStatus()
  }, [])

  useEffect(() => {
    void loadMemoryNarrativeSummary()
  }, [])

  const currentGroups = tab === "active" || tab === "archived" ? data?.[tab] || {} : {}

  const insightCards = useMemo(
    () => buildMemoryInsightCards(data, quality, memoryHealthStatus),
    [data, quality, memoryHealthStatus],
  )

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
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
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

  function clearVerifiedMemoryPinSession() {
    setVerifiedMemoryPin(null)
    setMemoryPinSessionNotice(null)
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

    if (verifiedMemoryPin) {
      void action(verifiedMemoryPin).catch((err) => {
        clearVerifiedMemoryPinSession()
        setError(err instanceof Error ? err.message : "Memory PIN session failed")
        setPinInput("")
        setPinModal({
          title,
          description:
            "Your Memory PIN session was rejected or expired. Please enter your 6-digit Memory PIN again.",
          action,
        })
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
    issueKey,
    pin,
  }: {
    actionName: "keep_one_archive_rest" | "archive_memory"
    keepMemoryId?: string | null
    archiveMemoryIds: string[]
    issueKey?: string
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

      if (issueKey) {
        setResolvedQualityIssueKeys((prev) => ({ ...prev, [issueKey]: true }))
      }

      const archivedCount = archiveMemoryIds.length
      setMemoryActionNotice(
        actionName === "keep_one_archive_rest"
          ? `Resolved memory issue. Kept one source of truth and archived ${archivedCount} duplicate/conflicting memor${archivedCount === 1 ? "y" : "ies"}.`
          : `Archived ${archivedCount} memor${archivedCount === 1 ? "y" : "ies"} from review.`,
      )

      await load()
      await loadQuality()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to resolve memory issue")
    } finally {
      setSavingId(null)
    }
  }

  async function confirmMemoryFreshness(
    memoryId: string,
    issueKey: string | undefined,
    pin: string,
  ) {
    setSavingId(memoryId)
    setError(null)

    try {
      const res = await fetch(`/api/memory-review/${memoryId}/confirm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pin }),
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

  return (
    <main className="min-h-screen px-4 py-6 text-slate-950 dark:text-slate-900 dark:text-zinc-100 sm:px-6 lg:px-8">
      <div className="mx-auto flex max-w-7xl flex-col gap-6">
        <header className="rounded-[2rem] border border-slate-300/55 bg-slate-50/[0.86] p-6 shadow-2xl shadow-slate-900/10 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/[0.68] dark:shadow-black/30">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div>
              <p className="text-sm uppercase tracking-[0.28em] text-cyan-700 dark:text-cyan-300/80">
                {memoriesEyebrow}
              </p>
              <h1 className="mt-3 text-3xl font-semibold tracking-tight text-slate-950 dark:text-white sm:text-4xl">
                Memories
              </h1>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-700 dark:text-zinc-300">
                Everything {assistantName} remembers about you — and how it all connects.
              </p>
              {loading && data ? (
                <p className="mt-2 text-xs text-slate-500 dark:text-zinc-400">
                  Showing saved snapshot while refreshing latest memories…
                </p>
              ) : null}
            </div>

            <div className="flex flex-wrap gap-3">
              <BackToLastChat className="inline-flex h-10 items-center justify-center rounded-full border border-border bg-fg/[0.035] px-4 text-sm font-medium text-fg-muted shadow-sm transition hover:bg-fg/5 hover:text-fg focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/60 active:scale-[0.98]">
                Back to Chat
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
                className="inline-flex items-center gap-2 rounded-full border border-slate-300/55 bg-slate-50/[0.84] px-4 py-2 text-sm font-medium text-slate-700 shadow-sm shadow-slate-900/5 transition hover:bg-white dark:border-white/10 dark:bg-slate-950/[0.68] dark:text-zinc-200 dark:hover:bg-white/10"
              >
                <PlusCircle className="h-4 w-4" />
                Add memory
              </button>

              <div className="group relative inline-flex">
                <button
                  onClick={() => void consolidateMemories()}
                  disabled={consolidating || loading}
                  aria-describedby="consolidate-tooltip"
                  className="inline-flex items-center gap-2 rounded-full border border-slate-300/55 bg-slate-50/[0.84] px-4 py-2 text-sm font-medium text-slate-700 shadow-sm shadow-slate-900/5 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-60 dark:border-white/10 dark:bg-slate-950/[0.68] dark:text-zinc-200 dark:hover:bg-white/10"
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
                  className="pointer-events-none absolute right-0 top-full z-30 mt-2 w-64 rounded-2xl border border-slate-300/55 bg-white/95 px-3 py-2 text-xs leading-5 text-slate-600 opacity-0 shadow-xl shadow-slate-900/10 backdrop-blur-xl transition group-hover:opacity-100 dark:border-white/10 dark:bg-zinc-950/95 dark:text-zinc-300"
                >
                  Creates a clearer summary from repeated memory patterns.
                </div>
              </div>

              <button
                onClick={() => void load()}
                disabled={loading}
                className="inline-flex items-center gap-2 rounded-full bg-cyan-400 px-4 py-2 text-sm font-medium text-zinc-950 transition hover:bg-cyan-300 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {loading && !data ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCcw className="h-4 w-4" />
                )}
                Refresh
              </button>
            </div>
          </div>

          <div className="mt-6 grid gap-3 sm:grid-cols-5">
            <StatCard label="Remembered" value={activeCount} />
            <StatCard label="Set aside" value={archivedCount} />
            <StatCard label="Worth checking" value={reviewCount} />
            <StatCard label="Total" value={data?.counts?.total ?? 0} />
          </div>

          <p className="mt-3 text-xs leading-5 text-slate-500 dark:text-zinc-400">
            Use this space to remember, explore, and gently improve what {assistantName} knows about you.
          </p>

          {reviewCount > 0 ? (
            <div className="mt-4 rounded-2xl border border-cyan-200/80 bg-cyan-50/[0.92] p-4 text-sm leading-6 text-cyan-950 shadow-sm shadow-cyan-900/5 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
              Aliyya found {reviewCount} memor
              {reviewCount === 1 ? "y" : "ies"} worth checking.
              Open Review & improve when you want to clean them up safely.
            </div>
          ) : null}
        </header>

        <section className="flex flex-col gap-3 rounded-[1.5rem] border border-slate-300/55 bg-slate-50/[0.84] p-4 shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035] md:flex-row md:items-center md:justify-between">
          <div className="flex rounded-full border border-slate-300/55 dark:border-white/10 bg-slate-50/[0.84] dark:bg-slate-950/[0.62] p-1">
            <TabButton
              active={tab === "active"}
              onClick={() => {
                setTab("active")
                setMemoryActionNotice(null)
              }}
              label={`Remembered (${activeCount})`}
            />
            <TabButton
              active={tab === "graph"}
              onClick={() => {
                setTab("graph")
                setMemoryActionNotice(null)
                if (!graphView && !graphLoading) void loadMemoryGraphView()
              }}
              label="Memory Map"
            />
            <TabButton
              active={tab === "review"}
              onClick={() => {
                setTab("review")
                setMemoryActionNotice(null)
              }}
              label={`Review & improve (${reviewCount})`}
            />
            <TabButton
              active={tab === "archived"}
              onClick={() => {
                setTab("archived")
                setMemoryActionNotice(null)
              }}
              label={`Archived (${archivedCount})`}
            />
          </div>

          <div className="relative w-full md:max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500 dark:text-zinc-500" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder={tab === "graph" ? "Search memory map..." : "Search memories..."}
              className="w-full rounded-full border border-slate-300/55 dark:border-white/10 bg-slate-50/[0.88] dark:bg-black/25 py-2 pl-10 pr-4 text-sm text-slate-950 dark:text-white outline-none placeholder:text-slate-500 dark:text-zinc-500 focus:border-cyan-300/70"
            />
          </div>
        </section>

        {tab !== "graph" ? (
          <MemoryNarrativeSummaryPanel
            assistantName={assistantName}
            summary={narrativeSummary}
            loading={narrativeLoading}
            regenerating={narrativeRegenerating}
            onRegenerate={() => void regenerateMemoryNarrativeSummary()}
          />
        ) : null}

        {error ? (
          <div className="rounded-2xl border border-red-400/40 bg-red-50 p-4 text-sm text-red-700 dark:border-red-400/30 dark:bg-red-500/10 dark:text-red-100">
            {error}
          </div>
        ) : null}

        {memoryActionNotice ? (
          <div className="rounded-2xl border border-emerald-200/70 bg-emerald-50/80 p-4 text-sm leading-6 text-emerald-800 shadow-sm shadow-emerald-900/5 dark:border-emerald-300/15 dark:bg-emerald-300/10 dark:text-emerald-100">
            {memoryActionNotice}
          </div>
        ) : null}

        {memoryPinSessionNotice ? (
          <div className="flex items-center justify-between gap-3 rounded-2xl border border-cyan-200/70 bg-cyan-50/80 p-4 text-sm leading-6 text-cyan-800 shadow-sm shadow-cyan-900/5 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
            <span>{memoryPinSessionNotice}</span>
            <button
              type="button"
              onClick={clearVerifiedMemoryPinSession}
              className="rounded-full border border-cyan-200 bg-slate-50/[0.84] px-3 py-1 text-xs font-medium text-cyan-700 transition hover:bg-white dark:border-cyan-300/20 dark:bg-white/10 dark:text-cyan-100 dark:hover:bg-white/15"
            >
              Lock
            </button>
          </div>
        ) : null}

        {tab === "graph" ? (
          <MemoryGraphViewPanel
            payload={graphView}
            loading={graphLoading}
            hasVerifiedPin={Boolean(verifiedMemoryPin)}
            query={query}
            sectionFilter={graphSectionFilter}
            onSectionFilterChange={setGraphSectionFilter}
            showDetails={showGraphDetails}
            onToggleDetails={() => setShowGraphDetails((value) => !value)}
            onUnlock={() => void loadMemoryGraphView()}
          />
        ) : tab === "review" ? (
          <MemoryQualityPanel
            assistantName={assistantName}
            quality={quality}
            loading={loading}
            saving={savingId === "quality-resolve"}
            resolvedIssueKeys={resolvedQualityIssueKeys}
            onConfirmMemory={(memoryId, issueKey) =>
              requireMemoryPin(
                "Confirm memory",
                "Enter your 6-digit Memory PIN to confirm this memory is still true.",
                async (pin) => {
                  await confirmMemoryFreshness(
                    memoryId,
                    issueKey,
                    pin,
                  )
                },
              )
            }
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
        ) : loading && Object.keys(filteredGroups).length === 0 ? (
          <LoadingState />
        ) : Object.keys(filteredGroups).length === 0 ? (
          <EmptyState tab={tab} query={query} />
        ) : (
          <section className="space-y-4">
            {GROUP_ORDER.filter((group) => filteredGroups[group]?.length).map(
              (group) => (
                <div
                  key={group}
                  className="overflow-hidden rounded-[1.5rem] border border-slate-300/55 bg-slate-50/[0.84] shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]"
                >
                  <button
                    onClick={() =>
                      setOpenGroups((prev) => ({
                        ...prev,
                        [group]: !prev[group],
                      }))
                    }
                    className="flex w-full items-center justify-between px-5 py-4 text-left transition hover:bg-slate-50/[0.86] dark:hover:bg-slate-950/[0.68]"
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
                    <div className="grid gap-3 border-t border-slate-300/55 dark:border-white/10 p-4 lg:grid-cols-2">
                      {filteredGroups[group].map((memory) => (
                        <MemoryCard
                          key={memory.id}
                          memory={memory}
                          tab={tab}
                          saving={savingId === memory.id}
                          onConfirm={() =>
                            requireMemoryPin(
                              "Confirm memory",
                              "Enter your 6-digit Memory PIN to confirm this memory is still true.",
                              async (pin) => {
                                await action(memory, "confirm", pin)
                              },
                            )
                          }
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
              if (pinStatus?.memory_pin_enabled !== false && pinInput.trim().length === 6) {
                setVerifiedMemoryPin(pinInput)
                setMemoryPinSessionNotice("Memory PIN verified for this page session.")
              }
              setPinModal(null)
              setPinInput("")
            } catch (err) {
              clearVerifiedMemoryPinSession()
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
                  setMemoryPinSessionNotice("Memory PIN verified for this page session.")
                  setManualAddOpen(true)
                },
              )
              return
            }

            await addManualMemory(verifiedMemoryPin)
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
                      }}
          onSave={() => void saveEdit()}
        />
      ) : null}
    </main>
  )
}


function MemoryInsightSummary({
  cards,
  onFocus,
}: {
  cards: MemoryInsightCard[]
  onFocus: (card: MemoryInsightCard) => void
}) {
  return (
    <section className="rounded-[1.75rem] border border-slate-300/55 bg-slate-50/[0.86] p-5 shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/[0.72]">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-zinc-500">
            Memory intelligence
          </p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
            <AssistantNameInline />’s understanding of you
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-zinc-400">
            A quick, transparent summary of the active memories that shape future answers.
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {cards.map((card) => (
          <button
            key={card.key}
            type="button"
            onClick={() => onFocus(card)}
            className="group rounded-2xl border border-slate-300/55 bg-slate-50/[0.86] p-4 text-left transition hover:-translate-y-0.5 hover:border-slate-300 hover:bg-white hover:shadow-lg hover:shadow-slate-900/5 dark:border-white/10 dark:bg-white/[0.035] dark:hover:border-white/20 dark:hover:bg-white/[0.07]"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="text-sm font-semibold text-slate-950 dark:text-white">
                  {card.title}
                </p>
                <p className="mt-1 text-xs leading-5 text-slate-500 dark:text-zinc-400">
                  {card.description}
                </p>
              </div>
              <span className={[
                "rounded-full px-2.5 py-1 text-xs font-semibold",
                card.key === "needs-review" && card.count > 0
                  ? "bg-amber-100 text-amber-800 dark:bg-amber-300/15 dark:text-cyan-100"
                  : "bg-slate-200/80 text-slate-700 dark:bg-white/10 dark:text-zinc-200",
              ].join(" ")}>
                {card.count}
              </span>
            </div>

            <div className="mt-3 space-y-1.5">
              {card.sample.length > 0 ? (
                card.sample.map((item, index) => (
                  <p
                    key={`${card.key}-sample-${index}`}
                    className="line-clamp-1 text-xs text-slate-600 dark:text-zinc-300"
                  >
                    · {item}
                  </p>
                ))
              ) : (
                <p className="text-xs text-slate-400 dark:text-zinc-500">
                  No active memory in this area yet.
                </p>
              )}
            </div>

            <p className="mt-3 text-xs font-medium text-slate-500 transition group-hover:text-slate-950 dark:text-zinc-500 dark:group-hover:text-white">
              Review & improve →
            </p>
          </button>
        ))}
      </div>
    </section>
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
          ? "border-amber-400/30 bg-cyan-50/[0.92] text-amber-800 dark:border-amber-300/20 dark:bg-cyan-300/10 dark:text-cyan-100"
          : "border-slate-300/55 dark:border-white/10 bg-slate-50/[0.88] dark:bg-white/[0.06] text-slate-700 dark:text-zinc-300",
      ].join(" ")}
    >
      {children}
    </span>
  )
}


function LoadingState() {
  return (
    <div className="rounded-[1.5rem] border border-slate-300/55 bg-slate-50/[0.84] p-6 shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]">
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
    <div className="rounded-[1.5rem] border border-slate-300/55 bg-slate-50/[0.84] p-8 text-center shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]">
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

async function safeDetail(res: Response) {
  try {
    const json = await res.json()
    return json?.detail || json?.message || null
  } catch {
    return null
  }
}


function AssistantNameInline() {
  const assistantName = useAssistantDisplayName();
  return <>{assistantName || "your assistant"}</>;
}

