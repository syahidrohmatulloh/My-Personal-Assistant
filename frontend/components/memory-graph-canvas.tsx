'use client'

type GraphSectionKey = "notes" | "types" | "tags" | "entities" | "timeline" | "candidate_backlinks"
type GraphSectionFilter = GraphSectionKey | "all"
type GraphRecord = Record<string, unknown>

type MemoryGraphCanvasPayload = {
  sections?: Partial<Record<GraphSectionKey, GraphRecord[]>> | null
}

type NodeKind = "note" | "type" | "tag" | "entity" | "timeline"

type VisualNode = {
  id: string
  kind: NodeKind
  label: string
  detail: string
  searchText: string
  x: number
  y: number
}

type VisualEdge = {
  id: string
  sourceId: string
  targetId: string
}

const RESOURCE_SECTIONS: GraphSectionKey[] = ["types", "tags", "entities", "timeline"]
const MAX_NOTES = 18
const MAX_RESOURCE_ITEMS = 16
const MAX_EDGES = 80

export function MemoryGraphCanvas({
  payload,
  query,
  sectionFilter,
}: {
  payload: MemoryGraphCanvasPayload | null
  query: string
  sectionFilter: GraphSectionFilter
}) {
  if (!payload) return null

  const graph = buildGraph(payload, query, sectionFilter)

  return (
    <div className="mt-5 rounded-2xl border border-slate-200/70 bg-slate-950/[0.02] p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
            Visual map
          </p>
          <h3 className="mt-1 text-sm font-semibold text-slate-950 dark:text-white">
            Projected node-link view
          </h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500 dark:text-zinc-400">
            Read-only SVG layout from the loaded graph payload. Search and section filters are applied locally.
          </p>
        </div>
        <div className="flex flex-wrap gap-2 text-xs text-slate-500 dark:text-zinc-400">
          <span className="rounded-full border border-slate-200/70 bg-white/70 px-2.5 py-1 dark:border-white/10 dark:bg-white/[0.05]">
            {graph.nodes.length} nodes
          </span>
          <span className="rounded-full border border-slate-200/70 bg-white/70 px-2.5 py-1 dark:border-white/10 dark:bg-white/[0.05]">
            {graph.edges.length} edges
          </span>
        </div>
      </div>

      {graph.nodes.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-200/80 p-4 text-xs leading-5 text-slate-400 dark:border-white/10 dark:text-zinc-500">
          No visual graph items match the current search/filter.
        </div>
      ) : (
        <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200/70 bg-white/80 dark:border-white/10 dark:bg-black/20">
          <svg
            aria-label="Read-only memory graph visualization"
            className="h-[360px] w-full"
            role="img"
            viewBox="0 0 900 420"
          >
            <rect className="fill-white dark:fill-zinc-950" height="420" width="900" />
            {graph.edges.map((edge) => {
              const source = graph.nodeById.get(edge.sourceId)
              const target = graph.nodeById.get(edge.targetId)
              if (!source || !target) return null
              return (
                <line
                  key={edge.id}
                  className="stroke-slate-300 dark:stroke-white/20"
                  strokeWidth="1.2"
                  x1={source.x}
                  x2={target.x}
                  y1={source.y}
                  y2={target.y}
                />
              )
            })}
            {graph.nodes.map((node) => (
              <g key={node.id} transform={`translate(${node.x} ${node.y})`}>
                <title>{[node.label, node.detail].filter(Boolean).join(" · ")}</title>
                {node.kind === "note" ? (
                  <circle className={nodeClassName(node.kind)} r="22" />
                ) : (
                  <rect className={nodeClassName(node.kind)} height="34" rx="17" width="118" x="-59" y="-17" />
                )}
                <text
                  className="pointer-events-none fill-slate-900 text-[10px] font-semibold dark:fill-zinc-50"
                  dominantBaseline="middle"
                  textAnchor="middle"
                  y={node.kind === "note" ? -2 : -3}
                >
                  {truncate(node.label, node.kind === "note" ? 12 : 18)}
                </text>
                <text
                  className="pointer-events-none fill-slate-500 text-[8px] dark:fill-zinc-400"
                  dominantBaseline="middle"
                  textAnchor="middle"
                  y={node.kind === "note" ? 11 : 9}
                >
                  {node.kind}
                </text>
              </g>
            ))}
          </svg>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-zinc-500">
        <span>Notes are centered.</span>
        <span>Tags/types/timeline/entities surround them.</span>
        <span>Candidate backlinks and index relationships are shown as edges.</span>
      </div>
    </div>
  )
}

function buildGraph(payload: MemoryGraphCanvasPayload, query: string, sectionFilter: GraphSectionFilter) {
  const allNodes = new Map<string, VisualNode>()
  const allEdges: VisualEdge[] = []
  const notesByRawId = new Map<string, GraphRecord>()

  items(payload, "notes").forEach((note, index) => {
    const rawId = text(note, "id") || `note-${index + 1}`
    notesByRawId.set(rawId, note)
  })

  const showAll = sectionFilter === "all"
  const showNotes = showAll || sectionFilter === "notes"

  if (showNotes) {
    Array.from(notesByRawId.entries())
      .slice(0, MAX_NOTES)
      .forEach(([rawId, note]) => addNoteNode(allNodes, rawId, note))
  }

  for (const section of RESOURCE_SECTIONS) {
    if (!showAll && sectionFilter !== section) continue

    items(payload, section)
      .slice(0, MAX_RESOURCE_ITEMS)
      .forEach((item) => {
        const resource = resourceNode(section, item)
        if (!resource) return
        allNodes.set(resource.id, resource)

        ids(item, "note_ids")
          .slice(0, MAX_NOTES)
          .forEach((rawNoteId) => {
            const note = notesByRawId.get(rawNoteId)
            if (!note) return
            addNoteNode(allNodes, rawNoteId, note)
            allEdges.push({
              id: `${resource.id}->note:${rawNoteId}`,
              sourceId: resource.id,
              targetId: `note:${rawNoteId}`,
            })
          })
      })
  }

  if (showAll || sectionFilter === "candidate_backlinks") {
    items(payload, "candidate_backlinks")
      .slice(0, MAX_EDGES)
      .forEach((link) => {
        const sourceRawId = text(link, "source_note_id")
        const targetRawId = text(link, "target_note_id")
        const sourceNote = notesByRawId.get(sourceRawId)
        const targetNote = notesByRawId.get(targetRawId)
        if (!sourceRawId || !targetRawId || !sourceNote || !targetNote) return

        addNoteNode(allNodes, sourceRawId, sourceNote)
        addNoteNode(allNodes, targetRawId, targetNote)
        allEdges.push({
          id: `backlink:${sourceRawId}->${targetRawId}`,
          sourceId: `note:${sourceRawId}`,
          targetId: `note:${targetRawId}`,
        })
      })
  }

  const q = query.trim().toLowerCase()
  const visibleIds = new Set<string>()

  for (const node of allNodes.values()) {
    if (!q || node.searchText.includes(q)) visibleIds.add(node.id)
  }

  if (q) {
    for (const edge of allEdges) {
      if (visibleIds.has(edge.sourceId) || visibleIds.has(edge.targetId)) {
        visibleIds.add(edge.sourceId)
        visibleIds.add(edge.targetId)
      }
    }
  }

  const visibleNodes = Array.from(allNodes.values()).filter((node) => visibleIds.has(node.id))
  const nodeIds = new Set(visibleNodes.map((node) => node.id))
  const visibleEdges = allEdges
    .filter((edge) => nodeIds.has(edge.sourceId) && nodeIds.has(edge.targetId))
    .slice(0, MAX_EDGES)

  const nodes = layout(visibleNodes)
  const nodeById = new Map(nodes.map((node) => [node.id, node]))

  return { nodes, edges: visibleEdges, nodeById }
}

function addNoteNode(nodes: Map<string, VisualNode>, rawId: string, note: GraphRecord) {
  const id = `note:${rawId}`
  if (nodes.has(id)) return

  const label = text(note, "title") || text(note, "body_preview") || "Untitled note"
  const detail = [text(note, "note_type"), ids(note, "tags").slice(0, 3).join(", ")]
    .filter(Boolean)
    .join(" · ")

  nodes.set(id, {
    id,
    kind: "note",
    label,
    detail,
    searchText: [rawId, label, detail, text(note, "body_preview")].join(" ").toLowerCase(),
    x: 450,
    y: 210,
  })
}

function resourceNode(section: GraphSectionKey, item: GraphRecord): VisualNode | null {
  if (section === "types") {
    const value = text(item, "type") || "unknown"
    return makeResourceNode(`type:${value}`, "type", value, `${text(item, "count")} notes`, item)
  }

  if (section === "tags") {
    const value = text(item, "tag")
    if (!value) return null
    return makeResourceNode(`tag:${value}`, "tag", value, `${text(item, "count")} notes`, item)
  }

  if (section === "entities") {
    const key = text(item, "entity_key") || text(item, "entity_name")
    const label = text(item, "entity_name") || key
    if (!key || !label) return null
    return makeResourceNode(`entity:${key}`, "entity", label, text(item, "entity_type"), item)
  }

  if (section === "timeline") {
    const value = text(item, "date")
    if (!value) return null
    return makeResourceNode(`timeline:${value}`, "timeline", value, `${text(item, "count")} notes`, item)
  }

  return null
}

function makeResourceNode(id: string, kind: NodeKind, label: string, detail: string, item: GraphRecord): VisualNode {
  return {
    id,
    kind,
    label,
    detail,
    searchText: [id, label, detail, ids(item, "note_ids").join(" ")].join(" ").toLowerCase(),
    x: 450,
    y: 210,
  }
}

function layout(nodes: VisualNode[]) {
  const notes = nodes.filter((node) => node.kind === "note")
  const resources = nodes.filter((node) => node.kind !== "note")
  const out: VisualNode[] = []

  notes.forEach((node, index) => {
    const angle = notes.length <= 1 ? 0 : (Math.PI * 2 * index) / notes.length
    const radiusX = notes.length <= 4 ? 110 : 155
    const radiusY = notes.length <= 4 ? 70 : 105
    out.push({
      ...node,
      x: Math.round(450 + Math.cos(angle) * radiusX),
      y: Math.round(210 + Math.sin(angle) * radiusY),
    })
  })

  const groups: Record<Exclude<NodeKind, "note">, VisualNode[]> = {
    type: [],
    tag: [],
    entity: [],
    timeline: [],
  }

  resources.forEach((node) => {
    if (node.kind === "note") return
    groups[node.kind].push(node)
  })

  layoutTop(groups.type).forEach((node) => out.push(node))
  layoutLeft(groups.tag).forEach((node) => out.push(node))
  layoutRight(groups.entity).forEach((node) => out.push(node))
  layoutBottom(groups.timeline).forEach((node) => out.push(node))

  return out
}

function layoutTop(nodes: VisualNode[]) {
  return nodes.map((node, index) => ({
    ...node,
    x: spread(index, nodes.length, 250, 650),
    y: 58,
  }))
}

function layoutLeft(nodes: VisualNode[]) {
  return nodes.map((node, index) => ({
    ...node,
    x: 105,
    y: spread(index, nodes.length, 125, 310),
  }))
}

function layoutRight(nodes: VisualNode[]) {
  return nodes.map((node, index) => ({
    ...node,
    x: 795,
    y: spread(index, nodes.length, 125, 310),
  }))
}

function layoutBottom(nodes: VisualNode[]) {
  return nodes.map((node, index) => ({
    ...node,
    x: spread(index, nodes.length, 250, 650),
    y: 362,
  }))
}

function spread(index: number, total: number, min: number, max: number) {
  if (total <= 1) return Math.round((min + max) / 2)
  return Math.round(min + ((max - min) * index) / (total - 1))
}

function items(payload: MemoryGraphCanvasPayload, key: GraphSectionKey) {
  const raw = payload.sections?.[key]
  return Array.isArray(raw) ? raw.filter(isRecord) : []
}

function isRecord(value: unknown): value is GraphRecord {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}

function text(item: GraphRecord, key: string) {
  const value = item[key]
  if (value == null || typeof value === "object") return ""
  return String(value).trim()
}

function ids(item: GraphRecord, key: string) {
  const value = item[key]
  if (!Array.isArray(value)) return []
  return value.map((entry) => String(entry ?? "").trim()).filter(Boolean)
}

function truncate(value: string, max: number) {
  const clean = value.trim()
  if (clean.length <= max) return clean
  return `${clean.slice(0, Math.max(0, max - 1)).trim()}…`
}

function nodeClassName(kind: NodeKind) {
  if (kind === "note") return "fill-white stroke-cyan-400 stroke-2 dark:fill-zinc-900 dark:stroke-cyan-300"
  if (kind === "entity") return "fill-white stroke-violet-300 stroke-1.5 dark:fill-zinc-900 dark:stroke-violet-300/80"
  if (kind === "timeline") return "fill-white stroke-amber-300 stroke-1.5 dark:fill-zinc-900 dark:stroke-amber-300/80"
  if (kind === "tag") return "fill-white stroke-emerald-300 stroke-1.5 dark:fill-zinc-900 dark:stroke-emerald-300/80"
  return "fill-white stroke-slate-300 stroke-1.5 dark:fill-zinc-900 dark:stroke-white/30"
}
