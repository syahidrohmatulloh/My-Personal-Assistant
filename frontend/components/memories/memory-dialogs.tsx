"use client"

import { Loader2, ShieldCheck, X } from "lucide-react"
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

function humanizeLabel(value?: string | null) {
  if (!value) return "—"
  return value
    .split("_")
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ")
}

export function MemoryPinDialog({
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
      <div className="w-full max-w-md rounded-[1.5rem] border border-slate-300/55 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-[#10101c]">
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
            className="mt-2 w-full rounded-2xl border border-slate-300/55 bg-slate-50/[0.88] p-3 text-center text-lg tracking-[0.4em] text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
          />
        </label>

        <div className="mt-6 flex flex-col justify-end gap-3 sm:flex-row">
          <button
            onClick={onCancel}
            disabled={saving}
            className="rounded-full border border-slate-300/55 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
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

export function ManualAddDialog({
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
      <div className="w-full max-w-2xl rounded-[1.5rem] border border-slate-300/55 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-[#10101c]">
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
              className="mt-2 w-full rounded-2xl border border-slate-300/55 bg-slate-50/[0.88] p-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
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
            className="rounded-full border border-slate-300/55 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
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

export function EditDialog({
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
      <div className="w-full max-w-2xl rounded-[1.5rem] border border-slate-300/55 bg-white p-5 shadow-2xl dark:border-white/10 dark:bg-[#10101c]">
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
              className="mt-2 w-full rounded-2xl border border-slate-300/55 bg-slate-50/[0.88] p-3 text-sm text-slate-900 outline-none placeholder:text-slate-400 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20 dark:border-white/10 dark:bg-black/25 dark:text-white dark:placeholder:text-zinc-500"
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
            className="rounded-full border border-slate-300/55 px-4 py-2 text-sm text-slate-600 hover:bg-slate-100 disabled:opacity-50 dark:border-white/10 dark:text-zinc-300 dark:hover:bg-white/10"
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
