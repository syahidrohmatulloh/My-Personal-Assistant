"use client"

import { MemoryGraphCanvas } from "../memory-graph-canvas"

export type MemoryGraphSectionKey = "notes" | "types" | "tags" | "entities" | "timeline" | "candidate_backlinks"
export type MemoryGraphSectionFilter = MemoryGraphSectionKey | "all"

export type MemoryGraphViewPayload = {
  read_only?: boolean
  runtime_retrieval_change?: boolean
  schema_migration?: boolean
  summary?: Record<string, unknown> | null
  sections?: Partial<Record<MemoryGraphSectionKey, Record<string, unknown>[]>> | null
}

const GRAPH_SECTION_LABELS: Record<MemoryGraphSectionKey, string> = {
  notes: "Memories",
  types: "Categories",
  tags: "Tags",
  entities: "People & topics",
  timeline: "Dates",
  candidate_backlinks: "Suggested links",
}


const GRAPH_SECTION_FILTERS: Array<{ key: MemoryGraphSectionFilter; label: string }> = [
  { key: "all", label: "All" },
  { key: "notes", label: "Memories" },
  { key: "types", label: "Categories" },
  { key: "tags", label: "Tags" },
  { key: "entities", label: "People & topics" },
  { key: "timeline", label: "Dates" },
  { key: "candidate_backlinks", label: "Suggested links" },
]



export const DEFAULT_GRAPH_SECTION_FILTER: MemoryGraphSectionFilter = "notes"
function memoryGraphItems(payload: MemoryGraphViewPayload | null, key: MemoryGraphSectionKey) {
  const items = payload?.sections?.[key]
  return Array.isArray(items) ? items : []
}

function memoryGraphItemTitle(item: Record<string, unknown>, index: number) {
  const candidates = [item["title"], item["label"], item["name"], item["key"], item["id"]]
  for (const candidate of candidates) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim()
  }
  return `Item ${index + 1}`
}



function memoryGraphItemSearchText(item: Record<string, unknown>) {
  const parts: string[] = []
  for (const value of Object.values(item)) {
    if (value == null) continue
    if (Array.isArray(value)) {
      parts.push(value.map((entry) => String(entry ?? "")).join(" "))
      continue
    }
    if (typeof value === "object") {
      continue
    }
    parts.push(String(value))
  }
  return parts.join(" ").toLowerCase()
}

function memoryGraphFilteredItems(
  payload: MemoryGraphViewPayload | null,
  key: MemoryGraphSectionKey,
  query: string,
) {
  const items = memoryGraphItems(payload, key)
  const q = query.trim().toLowerCase()
  if (!q) return items
  return items.filter((item) => memoryGraphItemSearchText(item).includes(q))
}

function memoryGraphItemDetail(item: Record<string, unknown>) {
  const fields = [
    ["type", "Category"],
    ["note_type", "Memory type"],
    ["count", "Memories"],
    ["score", "Strength"],
    ["date", "Date"],
    ["tag", "Tag"],
    ["entity_name", "Topic"],
    ["entity_type", "Type"],
  ] as const

  return fields
    .map(([field, label]) => {
      const value = item[field]
      if (value == null || value === "") return null
      if (Array.isArray(value)) return `${label}: ${value.slice(0, 4).join(", ")}`
      if (typeof value === "object") return null
      return `${label}: ${String(value)}`
    })
    .filter(Boolean)
    .join(" · ")
}

export function MemoryGraphViewPanel({
  payload,
  loading,
  hasVerifiedPin,
  query,
  sectionFilter,
  onSectionFilterChange,
  showDetails,
  onToggleDetails,
  onUnlock,
}: {
  payload: MemoryGraphViewPayload | null
  loading: boolean
  hasVerifiedPin: boolean
  query: string
  sectionFilter: MemoryGraphSectionFilter
  onSectionFilterChange: (value: MemoryGraphSectionFilter) => void
  showDetails: boolean
  onToggleDetails: () => void
  onUnlock: () => void
}) {
  const sections: MemoryGraphSectionKey[] = ["notes", "types", "tags", "entities", "timeline", "candidate_backlinks"]
  const visibleSections = sectionFilter === "all" ? sections : sections.filter((section) => section === sectionFilter)
  const notes = memoryGraphFilteredItems(payload, "notes", query)
  const tags = memoryGraphFilteredItems(payload, "tags", query)
  const entities = memoryGraphFilteredItems(payload, "entities", query)
  const backlinks = memoryGraphFilteredItems(payload, "candidate_backlinks", query)

  return (
    <section className="rounded-[1.75rem] border border-slate-300/55 bg-slate-50/[0.88] p-5 shadow-xl shadow-cyan-950/10 backdrop-blur-xl dark:border-white/10 dark:bg-slate-950/[0.72]">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500 dark:text-zinc-500">
            Memory relationship view
          </p>
          <h2 className="mt-1 text-xl font-semibold tracking-tight text-slate-950 dark:text-white">
            Memory Map
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-slate-500 dark:text-zinc-400">
            Explore relationships across your saved memories, people, topics, dates, tags, and suggested links. This view is read-only.
          </p>
        </div>

        <button
          type="button"
          onClick={onUnlock}
          disabled={loading}
          className="inline-flex h-10 shrink-0 items-center justify-center rounded-full bg-cyan-400 px-4 text-xs font-medium text-zinc-950 shadow-sm transition hover:bg-cyan-300 disabled:cursor-wait disabled:opacity-70"
        >
          {loading ? "Loading map..." : hasVerifiedPin ? "Refresh map" : "Unlock map"}
        </button>
      </div>

      <div className="mt-5 grid gap-2 sm:grid-cols-4">
        <MiniMetric label="Memories" value={notes.length} />
        <MiniMetric label="Tags" value={tags.length} />
        <MiniMetric label="People & topics" value={entities.length} />
        <MiniMetric label="Suggested links" value={backlinks.length} />
      </div>

      <MemoryGraphCanvas payload={payload} query={query} sectionFilter={sectionFilter} />



      {payload ? (
        <div className="mt-5 flex flex-wrap gap-2">
          {GRAPH_SECTION_FILTERS.map((filter) => {
            const active = sectionFilter === filter.key
            const count =
              filter.key === "all"
                ? sections.reduce((sum, section) => sum + memoryGraphFilteredItems(payload, section, query).length, 0)
                : memoryGraphFilteredItems(payload, filter.key, query).length
            return (
              <button
                key={filter.key}
                type="button"
                onClick={() => onSectionFilterChange(filter.key)}
                className={[
                  "rounded-full border px-3 py-1.5 text-xs font-medium transition",
                  active
                    ? "border-slate-950 bg-slate-950 text-white dark:border-white dark:bg-white dark:text-zinc-950"
                    : "border-slate-300/55 bg-slate-50/[0.84] text-slate-600 hover:bg-white dark:border-white/10 dark:bg-slate-950/[0.68] dark:text-zinc-300 dark:hover:bg-white/10",
                ].join(" ")}
              >
                {filter.label} <span className="opacity-70">{count}</span>
              </button>
            )
          })}
        </div>
      ) : null}


      {!payload && !loading ? (
        <div className="mt-5 rounded-2xl border border-cyan-200/70 bg-cyan-50/80 p-5 text-sm leading-6 text-cyan-900 dark:border-cyan-300/15 dark:bg-cyan-300/10 dark:text-cyan-100">
          Unlock your Memory Map with your Memory PIN to explore how your saved memories relate to each other.
        </div>
      ) : null}

      {loading ? (
        <div className="mt-5 space-y-3 rounded-2xl border border-slate-300/55 bg-slate-50/[0.84] p-5 dark:border-white/10 dark:bg-black/15">
          <div className="h-4 w-5/6 animate-pulse rounded-full bg-slate-200 dark:bg-white/10" />
          <div className="h-4 w-4/6 animate-pulse rounded-full bg-slate-200 dark:bg-white/10" />
          <div className="h-4 w-3/4 animate-pulse rounded-full bg-slate-200 dark:bg-white/10" />
        </div>
      ) : null}

      {payload ? (
        <div className="mt-5 flex justify-end">
          <button
            type="button"
            onClick={onToggleDetails}
            className="rounded-full border border-slate-300/55 bg-slate-50/[0.86] px-3 py-1.5 text-xs font-medium text-slate-600 shadow-sm transition hover:bg-white dark:border-white/10 dark:bg-white/[0.06] dark:text-zinc-300 dark:hover:bg-white/10"
          >
            {showDetails ? "Hide details" : "Show relationship details"}
          </button>
        </div>
      ) : null}

      {payload && showDetails ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {visibleSections.map((sectionKey) => {
            const items = memoryGraphFilteredItems(payload, sectionKey, query)
            return (
              <div key={sectionKey} className="rounded-2xl border border-slate-300/55 bg-slate-50/[0.86] p-4 dark:border-white/10 dark:bg-slate-950/[0.62]">
                <div className="flex items-center justify-between gap-3">
                  <h3 className="text-sm font-semibold text-slate-950 dark:text-white">
                    {GRAPH_SECTION_LABELS[sectionKey]}
                  </h3>
                  <span className="rounded-full bg-slate-200/80 px-2.5 py-1 text-xs font-semibold text-slate-700 dark:bg-white/10 dark:text-zinc-200">
                    {items.length}
                  </span>
                </div>

                <div className="mt-3 space-y-2">
                  {items.slice(0, 8).map((item, index) => {
                    const detail = memoryGraphItemDetail(item)
                    return (
                      <div key={`${sectionKey}-${index}`} className="rounded-xl border border-slate-300/55 bg-slate-50/[0.88] p-3 dark:border-white/10 dark:bg-slate-950/[0.68]">
                        <p className="line-clamp-1 text-sm font-medium text-slate-900 dark:text-zinc-100">
                          {memoryGraphItemTitle(item, index)}
                        </p>
                        {detail ? (
                          <p className="mt-1 line-clamp-2 text-xs leading-5 text-slate-500 dark:text-zinc-400">
                            {detail}
                          </p>
                        ) : null}
                      </div>
                    )
                  })}

                  {items.length === 0 ? (
                    <p className="rounded-xl border border-dashed border-slate-300/60 p-3 text-xs leading-5 text-slate-400 dark:border-white/10 dark:text-zinc-500">
                      {query.trim() ? "No memory map items match this search." : "No items in this section yet."}
                    </p>
                  ) : null}
                </div>
              </div>
            )
          })}
        </div>
      ) : null}
    </section>
  )
}

function MiniMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-slate-300/55 bg-slate-50/[0.84] px-4 py-3 shadow-sm shadow-slate-900/5 backdrop-blur dark:border-white/10 dark:bg-white/[0.05]">
      <p className="text-[10px] font-semibold uppercase tracking-[0.16em] text-slate-500 dark:text-zinc-500">
        {label}
      </p>
      <p className="mt-1 text-lg font-semibold text-slate-950 dark:text-white">{value}</p>
    </div>
  )
}
