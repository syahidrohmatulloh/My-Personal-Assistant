"use client"

import { useState } from "react"
import type { ReactNode } from "react"
import { StatCard } from "./memory-page-primitives"
import { AlertTriangle, CheckCircle2 } from "lucide-react"
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

export type MemoryQualityReviewMemory = {
  id: string
  content: string
  category?: string | null
  structured_field?: string | null
  structured_value?: string | null
}

export type MemoryQualityReasonInfo = {
  main?: string
  field?: string | null
  values?: string[]
  reasons?: string[]
}

export type MemoryQualityReviewItem = {
  issue_type: "duplicate" | "conflict" | "low_quality" | string
  severity: "low" | "medium" | "high" | string
  memory_ids: string[]
  title: string
  explanation: string
  suggested_action: string
  reason?: MemoryQualityReasonInfo | null
  memories?: MemoryQualityReviewMemory[]
}

export type MemoryQualityPayload = {
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

function memoryQualityIssueKey(item: MemoryQualityReviewItem) {
  return [
    item.issue_type,
    item.severity,
    ...item.memory_ids.slice().sort(),
  ].join(":")
}

type MemoryReviewFilter =
  | "all"
  | "duplicate"
  | "conflict"
  | "low_quality"
  | "stale"
  | "high_priority"

const MEMORY_REVIEW_FILTERS: Array<{
  key: MemoryReviewFilter
  label: string
}> = [
  { key: "all", label: "All" },
  { key: "duplicate", label: "Duplicates" },
  { key: "conflict", label: "Conflicts" },
  { key: "low_quality", label: "Low quality" },
  { key: "stale", label: "Stale" },
  { key: "high_priority", label: "High priority" },
]

function memoryIssueSeverityRank(value?: string | null) {
  if (value === "high") return 3
  if (value === "medium") return 2
  if (value === "low") return 1
  return 0
}

function isStaleMemoryIssue(item: MemoryQualityReviewItem) {
  return item.issue_type === "stale" || item.issue_type === "stale_memory"
}

function matchesMemoryReviewFilter(item: MemoryQualityReviewItem, filter: MemoryReviewFilter) {
  if (filter === "all") return true
  if (filter === "high_priority") return item.severity === "high"
  if (filter === "stale") return isStaleMemoryIssue(item)
  return item.issue_type === filter
}

function sortMemoryReviewIssues(a: MemoryQualityReviewItem, b: MemoryQualityReviewItem) {
  const severityDelta = memoryIssueSeverityRank(b.severity) - memoryIssueSeverityRank(a.severity)
  if (severityDelta !== 0) return severityDelta

  const typeDelta = a.issue_type.localeCompare(b.issue_type)
  if (typeDelta !== 0) return typeDelta

  return a.title.localeCompare(b.title)
}

function formatDateTime(value?: string | null) {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}

export function MemoryQualityPanel({
  assistantName,
  quality,
  loading,
  saving,
  resolvedIssueKeys,
  onResolve,
  onConfirmMemory,
}: {
  assistantName: string
  quality: MemoryQualityPayload | null
  loading: boolean
  saving: boolean
  resolvedIssueKeys: Record<string, boolean>
  onResolve: (params: {
    actionName: "keep_one_archive_rest" | "archive_memory"
    keepMemoryId?: string | null
    archiveMemoryIds: string[]
    issueKey?: string
  }) => void
  onConfirmMemory: (memoryId: string, issueKey?: string) => void
}) {
  const [reviewFilter, setReviewFilter] = useState<MemoryReviewFilter>("all")

  if (loading) return <LoadingState />

  const unresolvedItems = (quality?.review_items || []).filter(
    (item) => !resolvedIssueKeys[memoryQualityIssueKey(item)],
  )

  const items = unresolvedItems
    .filter((item) => matchesMemoryReviewFilter(item, reviewFilter))
    .sort(sortMemoryReviewIssues)

  if (!quality || items.length === 0) {
    return (
      <div className="rounded-[1.5rem] border border-emerald-200/70 bg-emerald-50/70 p-8 text-center shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-emerald-300/15 dark:bg-emerald-300/10">
        <CheckCircle2 className="mx-auto h-8 w-8 text-emerald-600 dark:text-emerald-300" />
        <h2 className="mt-3 text-lg font-semibold text-slate-950 dark:text-white">
          {unresolvedItems.length === 0 ? "No memory issues found" : "No issues in this filter"}
        </h2>
        <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-slate-600 dark:text-zinc-300">
          {unresolvedItems.length === 0
              ? "The assistant did not find obvious duplicates, conflicts, stale, or unclear memories."
              : "Try another filter to review the remaining memory issues."}
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

      <div className="overflow-hidden rounded-[1.5rem] border border-slate-300/55 bg-slate-50/[0.84] shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-white/[0.035]">
        <div className="border-b border-slate-300/55 p-5 dark:border-white/10">
          <div className="flex items-center gap-3">
            <div className="rounded-2xl bg-amber-400/15 p-2 text-amber-700 dark:text-amber-300">
              <AlertTriangle className="h-5 w-5" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-slate-950 dark:text-white">
                Memory review console
              </h2>
              <p className="text-sm text-slate-500 dark:text-zinc-400">
                Look over memories that may need cleanup, such as duplicates, conflicts, stale details, or unclear notes. Actions are protected by your Memory PIN.
              </p>
            </div>
          </div>
        </div>

            <div className="flex flex-wrap gap-2">
              {MEMORY_REVIEW_FILTERS.map((filter) => {
                const count = unresolvedItems.filter((item) =>
                  matchesMemoryReviewFilter(item, filter.key),
                ).length
                const active = reviewFilter === filter.key

                return (
                  <button
                    key={filter.key}
                    type="button"
                    onClick={() => setReviewFilter(filter.key)}
                    className={[
                      "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                      active
                        ? "border-slate-900 bg-slate-900 text-white dark:border-white dark:bg-white dark:text-slate-950"
                        : "border-slate-200 bg-slate-50/[0.84] text-slate-600 hover:border-slate-300 hover:text-slate-950 dark:border-white/10 dark:bg-slate-950/[0.68] dark:text-zinc-300 dark:hover:border-white/20 dark:hover:text-white",
                    ].join(" ")}
                  >
                    {filter.label}
                    <span className="ml-1.5 opacity-70">{count}</span>
                  </button>
                )
              })}
            </div>

        <div className="grid gap-3 p-4">
          {items.map((item, index) => (
            <MemoryQualityIssueCard
              assistantName={assistantName}
              key={`${item.issue_type}-${index}`}
              item={item}
              issueKey={memoryQualityIssueKey(item)}
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

function memoryIssueActionLabel(item: MemoryQualityReviewItem) {
  if (item.issue_type === "duplicate") {
    return "Pick the clearest memory to keep, then archive the duplicates."
  }

  if (item.issue_type === "conflict") {
    return "Pick the memory that is currently correct, then archive the conflicting version."
  }

  if (item.issue_type === "stale_memory") {
    return "Confirm this is still true, or archive it if it is no longer relevant."
  }

  if (item.issue_type === "low_quality") {
    return "Archive this if it is vague, incomplete, or not useful for future conversations."
  }

  return "Look over this memory and choose the safest action."
}

function memoryIssuePrimaryAction(item: MemoryQualityReviewItem) {
  if (item.issue_type === "duplicate") return "Choose source of truth"
  if (item.issue_type === "conflict") return "Resolve conflict"
  if (item.issue_type === "stale_memory") return "Confirm or archive"
  if (item.issue_type === "low_quality") return "Clean up memory"
  return "Review safely"
}

function MemoryQualityIssueCard({
  assistantName,
  item,
  issueKey,
  saving,
  onResolve,
  onConfirmMemory,
}: {
  assistantName: string
  item: MemoryQualityReviewItem
  issueKey: string
  saving: boolean
  onResolve: (params: {
    actionName: "keep_one_archive_rest" | "archive_memory"
    keepMemoryId?: string | null
    archiveMemoryIds: string[]
    issueKey?: string
  }) => void
  onConfirmMemory: (memoryId: string, issueKey?: string) => void
}) {
  const severityClass =
    item.severity === "high"
      ? "border-red-200 bg-red-50 text-red-700 dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-200"
      : item.severity === "medium"
        ? "border-cyan-200/80 bg-cyan-50/[0.92] text-amber-700 dark:border-amber-400/20 dark:bg-cyan-50/[0.92]0/10 dark:text-amber-200"
        : "border-slate-200 bg-slate-50 text-slate-700 dark:border-white/10 dark:bg-slate-950/[0.68] dark:text-zinc-200"

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

  const actionLabel = memoryIssueActionLabel(item)
  const primaryAction = memoryIssuePrimaryAction(item)

  return (
    <article className="rounded-2xl border border-slate-300/55 bg-slate-50/[0.88] p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-slate-950/[0.62]">
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <span className={`rounded-full border px-2.5 py-1 text-xs font-medium ${severityClass}`}>
                {humanizeLabel(item.severity)}
              </span>
              <span className="rounded-full border border-slate-300/55 px-2.5 py-1 text-xs text-slate-500 dark:border-white/10 dark:text-zinc-400">
                {humanizeLabel(item.issue_type)}
              </span>
            </div>

            <h3 className="mt-3 text-base font-semibold text-slate-950 dark:text-white">
              {item.title}
            </h3>
            <p className="mt-1 text-sm leading-6 text-slate-600 dark:text-zinc-300">
              {item.explanation}
            </p>
            <div className="mt-3 rounded-2xl border border-cyan-200/80 bg-cyan-50/[0.92]/70 p-3 text-sm leading-6 text-amber-950 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
              <p className="font-medium">{primaryAction}</p>
              <p className="mt-1">{actionLabel}</p>
              <p className="mt-2 text-xs text-cyan-950/75 dark:text-cyan-100/75">
                {assistantName} suggestion: {item.suggested_action}
              </p>
            </div>

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
                className="rounded-2xl border border-slate-300/55 bg-slate-50/[0.86] p-3 dark:border-white/10 dark:bg-slate-950/[0.68]"
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
                      Option {index + 1}
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
                      className="shrink-0 rounded-full border border-slate-300/55 bg-white px-3 py-1.5 text-xs font-medium text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-white/10 dark:bg-slate-950/[0.68] dark:text-zinc-200 dark:hover:bg-white/10"
                    >
                      Keep this as source of truth
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
              Confirm still true
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
                  issueKey,
                })
              }
              disabled={saving}
              className="rounded-full border border-red-200 bg-red-50 px-3 py-1.5 text-xs font-medium text-red-700 transition hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-red-400/20 dark:bg-red-500/10 dark:text-red-200 dark:hover:bg-red-500/20"
            >
              Archive as no longer useful
            </button>
          </div>
        ) : null}

        {(canKeepOne || canConfirmStale || canArchiveSingle) ? (
          <p className="text-xs leading-5 text-slate-500 dark:text-zinc-500">
            Safe action: this does not permanently delete memory rows. Changes are archived or confirmed after Memory PIN approval.
          </p>
        ) : null}
      </div>
    </article>
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
