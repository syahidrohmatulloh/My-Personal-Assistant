"use client"

export type MemoryNarrativeSummary = {
  summary: string
  themes: string[]
  confidence_notes: string[]
  needs_review_notes: string[]
  memory_count: number
  generated_at: string
  source: "deterministic" | "llm" | string
  is_stale?: boolean
  latest_memory_changed_at?: string | null
}

export function MemoryNarrativeSummaryPanel({
  assistantName,
  summary,
  loading,
  regenerating,
  onRegenerate,
}: {
  assistantName: string
  summary: MemoryNarrativeSummary | null
  loading: boolean
  regenerating: boolean
  onRegenerate: () => void
}) {
  const paragraphs = summary?.summary
    ? summary.summary.split(/\n{2,}/).map((item) => item.trim()).filter(Boolean)
    : []

  return (
    <section className="rounded-[1.75rem] border border-slate-300/55 bg-slate-50/[0.88] p-5 shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/[0.72]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-zinc-500">
            Memory narrative
          </p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
            {assistantName}’s current understanding of you
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-zinc-400">
            A plain-English overview of {assistantName}’s current understanding. If something feels off, use Review & improve to clean the underlying memories.
          </p>
        </div>

        <button
          type="button"
          onClick={onRegenerate}
          disabled={regenerating}
          aria-busy={regenerating}
          className="inline-flex h-10 w-[168px] shrink-0 items-center justify-center rounded-full border border-slate-200 bg-white px-4 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:cursor-wait disabled:opacity-70 dark:border-white/10 dark:bg-white/10 dark:text-zinc-100 dark:hover:bg-white/15"
        >
          <span className="block truncate">
            {regenerating ? "Regenerating..." : "Regenerate summary"}
          </span>
        </button>
      </div>

      <div className="mt-5 rounded-2xl border border-slate-300/55 bg-slate-50/[0.84] p-5 dark:border-white/10 dark:bg-black/15">
        {loading ? (
          <div className="space-y-3">
            <div className="h-4 w-5/6 animate-pulse rounded-full bg-slate-200 dark:bg-white/10" />
            <div className="h-4 w-4/6 animate-pulse rounded-full bg-slate-200 dark:bg-white/10" />
            <div className="h-4 w-3/4 animate-pulse rounded-full bg-slate-200 dark:bg-white/10" />
          </div>
        ) : paragraphs.length ? (
          <div className="space-y-4 text-[15px] leading-8 text-slate-700 dark:text-zinc-200">
            {paragraphs.map((paragraph, index) => (
              <p key={`memory-narrative-${index}`}>{paragraph}</p>
            ))}
          </div>
        ) : (
          <p className="text-sm leading-7 text-slate-600 dark:text-zinc-300">
            {assistantName} does not yet have enough active memories to form a detailed narrative. As you chat and approve memories, this section will become more useful.
          </p>
        )}
      </div>

      {summary ? (
        <div className="mt-4 space-y-3">
          {summary.is_stale ? (
            <div className="rounded-2xl border border-cyan-200/80 bg-cyan-50/[0.92] p-3 text-xs leading-5 text-cyan-950 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
              This summary may be outdated because your memories changed after it was generated. Regenerate it when you want {assistantName} to refresh her understanding.
            </div>
          ) : null}

          {summary.themes?.length ? (
            <div className="flex flex-wrap gap-2">
              {summary.themes.slice(0, 8).map((theme) => (
                <span
                  key={theme}
                  className="rounded-full border border-slate-200 bg-slate-50/[0.86] px-3 py-1 text-xs font-medium text-slate-600 dark:border-white/10 dark:bg-white/[0.06] dark:text-zinc-300"
                >
                  {theme}
                </span>
              ))}
            </div>
          ) : null}

          {summary.needs_review_notes?.length ? (
            <div className="rounded-2xl border border-cyan-200/80 bg-cyan-50/[0.92]/70 p-3 text-xs leading-5 text-cyan-950 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
              {summary.needs_review_notes[0]}
            </div>
          ) : null}

          <p className="text-xs text-slate-400 dark:text-zinc-500">
            Based on {summary.memory_count} active memor{summary.memory_count === 1 ? "y" : "ies"} · Updated {formatDateTime(summary.generated_at)}
          </p>
        </div>
      ) : null}
    </section>
  )
}

function NarrativeMetaList({
  title,
  items,
  empty,
}: {
  title: string
  items: string[]
  empty: string
}) {
  return (
    <div className="rounded-2xl border border-slate-300/55 bg-slate-50/[0.84] p-3 dark:border-white/10 dark:bg-white/[0.035]">
      <p className="text-xs font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-500">
        {title}
      </p>
      <div className="mt-2 space-y-1.5">
        {items.length ? (
          items.slice(0, 5).map((item, index) => (
            <p key={`${title}-${index}`} className="text-xs leading-5 text-slate-600 dark:text-zinc-300">
              · {item}
            </p>
          ))
        ) : (
          <p className="text-xs leading-5 text-slate-400 dark:text-zinc-500">
            {empty}
          </p>
        )}
      </div>
    </div>
  )
}

function formatDateTime(value?: string | null) {
  if (!value) return "—"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString()
}
