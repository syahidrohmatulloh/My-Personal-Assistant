"use client"

import type { ReactNode } from "react"
import { CheckCircle2, Edit3, Loader2, RotateCcw, Trash2 } from "lucide-react"
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
  last_user_confirmed_at?: string | null
  last_user_confirmation_source?: string | null
  last_user_confirmation_evidence?: Record<string, unknown> | null
  created_at?: string | null
  updated_at?: string | null
  source?: string | null
  source_conversation_id?: string | null
}

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
    ? `Confirmed by you ${formatDate(memory.last_user_confirmed_at)}`
    : memory.created_at
      ? `Learned ${formatDate(memory.created_at)}`
      : "No date available"

  return {
    strength,
    source,
    confirmed,
  }
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

export function MemoryCard({
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
    <article className="flex min-h-64 flex-col justify-between rounded-2xl border border-slate-300/55 bg-slate-50/[0.86] p-4 shadow-sm shadow-slate-900/5 dark:border-white/10 dark:bg-slate-950/[0.62]">
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

        <MemoryTransparencyPanel memory={memory} />
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-slate-300/55 dark:border-white/10 pt-4">
        <div className="text-xs text-slate-500 dark:text-zinc-500">
          {memory.last_user_confirmed_at
            ? `Confirmed by you ${formatDate(memory.last_user_confirmed_at)}`
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
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={[
        "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition disabled:cursor-not-allowed disabled:opacity-50",
        danger
          ? "border-red-400/40 text-red-700 hover:bg-red-50 dark:border-red-400/30 dark:text-red-200 dark:hover:bg-red-500/10"
          : "border-slate-300/55 dark:border-white/10 text-slate-700 dark:text-zinc-200 hover:bg-slate-100 dark:bg-white/10",
      ].join(" ")}
    >
      {icon}
      {children}
    </button>
  )
}

function MemoryTransparencyPanel({ memory }: { memory: MemoryItem }) {
  const trust = memoryTrustSummary(memory)

  return (
    <div className="mt-4 rounded-xl border border-slate-300/55 bg-slate-50/[0.86] p-3 text-xs leading-5 text-slate-600 dark:border-white/10 dark:bg-white/[0.035] dark:text-zinc-300">
      <p className="font-medium text-slate-800 dark:text-zinc-100">
        Why this matters
      </p>
      <p className="mt-1">
        {memoryWhyItMatters(memory)}
      </p>

      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <div className="rounded-lg bg-slate-50/[0.84] px-2.5 py-2 dark:bg-slate-950/[0.62]">
          <p className="text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-zinc-500">
            Strength
          </p>
          <p className="mt-0.5 font-medium text-slate-700 dark:text-zinc-200">
            {trust.strength}
          </p>
        </div>
        <div className="rounded-lg bg-slate-50/[0.84] px-2.5 py-2 dark:bg-slate-950/[0.62]">
          <p className="text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-zinc-500">
            Source
          </p>
          <p className="mt-0.5 font-medium text-slate-700 dark:text-zinc-200">
            {trust.source}
          </p>
        </div>
        <div className="rounded-lg bg-slate-50/[0.84] px-2.5 py-2 dark:bg-slate-950/[0.62]">
          <p className="text-[10px] uppercase tracking-[0.14em] text-slate-400 dark:text-zinc-500">
            Freshness
          </p>
          <p className="mt-0.5 font-medium text-slate-700 dark:text-zinc-200">
            {trust.confirmed}
          </p>
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
