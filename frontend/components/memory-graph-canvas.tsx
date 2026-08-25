'use client'

import dynamic from "next/dynamic"
import { useEffect, useMemo, useRef, useState } from "react"

const ForceGraph2D = dynamic(
  () => import("react-force-graph-2d").then((mod) => mod.default as any),
  { ssr: false },
) as any

type GraphSectionKey = "notes" | "types" | "tags" | "entities" | "timeline" | "candidate_backlinks"
type GraphSectionFilter = GraphSectionKey | "all"
type GraphRecord = Record<string, unknown>

type MemoryGraphCanvasPayload = {
  sections?: Partial<Record<GraphSectionKey, GraphRecord[]>> | null
}

type NodeKind = "note" | "type" | "tag" | "entity" | "timeline"

type GraphNode = {
  id: string
  rawId: string
  kind: NodeKind
  label: string
  detail: string
  searchText: string
  val: number
  group: string
  x?: number
  y?: number
  fx?: number
  fy?: number
}

type GraphLink = {
  source: string | GraphNode
  target: string | GraphNode
  kind: "index" | "backlink"
  label: string
}

type BuiltGraph = {
  nodes: GraphNode[]
  links: GraphLink[]
  nodeById: Map<string, GraphNode>
}

const RESOURCE_SECTIONS: GraphSectionKey[] = ["types", "tags", "entities", "timeline"]
const MAX_NOTES = 80
const MAX_RESOURCE_ITEMS = 48
const MAX_LINKS = 220
const GRAPH_HEIGHT = 520

export function MemoryGraphCanvas({
  payload,
  query,
  sectionFilter,
}: {
  payload: MemoryGraphCanvasPayload | null
  query: string
  sectionFilter: GraphSectionFilter
}) {
  const graphRef = useRef<any>(null)
  const shellRef = useRef<HTMLDivElement | null>(null)
  const [width, setWidth] = useState(900)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [focusMode, setFocusMode] = useState(false)

  useEffect(() => {
    const element = shellRef.current
    if (!element) return

    const update = () => {
      const nextWidth = Math.floor(element.getBoundingClientRect().width)
      setWidth(Math.max(320, nextWidth))
    }

    update()

    const observer = new ResizeObserver(update)
    observer.observe(element)

    return () => observer.disconnect()
  }, [])

  const graph = useMemo(
    () => (payload ? buildGraph(payload, query, sectionFilter) : emptyGraph()),
    [payload, query, sectionFilter],
  )

  useEffect(() => {
    setSelectedId((current) => {
      if (!current) return current
      return graph.nodeById.has(current) ? current : null
    })
  }, [graph])

  const relatedIds = useMemo(() => relatedNodeIds(graph.links, selectedId), [graph.links, selectedId])
  const visibleGraph = useMemo(
    () => (focusMode && selectedId ? focusGraph(graph, selectedId, relatedIds) : graph),
    [focusMode, graph, relatedIds, selectedId],
  )

  const selectedNode = selectedId ? graph.nodeById.get(selectedId) || null : null

  if (!payload) return null

  const resetView = () => {
    setSelectedId(null)
    setHoveredId(null)
    setFocusMode(false)
    graphRef.current?.zoomToFit?.(600, 60)
  }

  const focusSelected = () => {
    if (!selectedNode) return
    setFocusMode(true)
    graphRef.current?.centerAt?.(selectedNode.x || 0, selectedNode.y || 0, 650)
    graphRef.current?.zoom?.(2.4, 650)
  }

  return (
    <div className="mt-5 rounded-2xl border border-slate-200/70 bg-slate-950/[0.02] p-4 dark:border-white/10 dark:bg-white/[0.03]">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
            Interactive memory map
          </p>
          <h3 className="mt-1 text-sm font-semibold text-slate-950 dark:text-white">
            Memory relationship map
          </h3>
          <p className="mt-1 max-w-2xl text-xs leading-5 text-slate-500 dark:text-zinc-400">
            Drag, zoom, pan, hover, and click to explore how your saved memories connect. This view is read-only.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <GraphPill>{visibleGraph.nodes.length} items</GraphPill>
          <GraphPill>{visibleGraph.links.length} connections</GraphPill>
          <button
            type="button"
            onClick={() => setFocusMode((value) => !value)}
            disabled={!selectedNode}
            className="rounded-full border border-slate-200/70 bg-white/70 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-white disabled:cursor-not-allowed disabled:opacity-40 dark:border-white/10 dark:bg-white/[0.05] dark:text-zinc-300 dark:hover:bg-white/10"
          >
            {focusMode ? "Exit focus" : "Focus item"}
          </button>
          <button
            type="button"
            onClick={resetView}
            className="rounded-full border border-slate-200/70 bg-white/70 px-3 py-1.5 text-xs font-medium text-slate-600 transition hover:bg-white dark:border-white/10 dark:bg-white/[0.05] dark:text-zinc-300 dark:hover:bg-white/10"
          >
            Reset view
          </button>
        </div>
      </div>

      {graph.nodes.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-slate-200/80 p-4 text-xs leading-5 text-slate-400 dark:border-white/10 dark:text-zinc-500">
          No memory map items match the current search/filter.
        </div>
      ) : (
        <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <div
            ref={shellRef}
            className="overflow-hidden rounded-2xl border border-slate-200/70 bg-white/90 dark:border-white/10 dark:bg-zinc-950"
          >
            <ForceGraph2D
              ref={graphRef}
              backgroundColor="rgba(0,0,0,0)"
              cooldownTicks={90}
              d3AlphaDecay={0.025}
              d3VelocityDecay={0.28}
              enableNodeDrag
              enablePanInteraction
              enableZoomInteraction
              graphData={visibleGraph}
              height={GRAPH_HEIGHT}
              linkColor={(link: GraphLink) => linkColor(link, selectedId, hoveredId, relatedIds)}
              linkDirectionalParticles={(link: GraphLink) => (isHighlightedLink(link, selectedId, hoveredId, relatedIds) ? 3 : 0)}
              linkDirectionalParticleSpeed={0.006}
              linkDirectionalParticleWidth={2.2}
              linkLabel={(link: GraphLink) => link.label}
              linkWidth={(link: GraphLink) => (isHighlightedLink(link, selectedId, hoveredId, relatedIds) ? 2.2 : 0.8)}
              nodeCanvasObject={(node: GraphNode, canvasContext: CanvasRenderingContext2D, globalScale: number) =>
                drawNode(node, canvasContext, globalScale, selectedId, hoveredId, relatedIds)
              }
              nodeId="id"
              nodeLabel={(node: GraphNode) => [node.label, node.detail].filter(Boolean).join(" · ")}
              nodeRelSize={5}
              onBackgroundClick={() => {
                setSelectedId(null)
                setHoveredId(null)
              }}
              onEngineStop={() => graphRef.current?.zoomToFit?.(350, 70)}
              onNodeClick={(node: GraphNode) => {
                setSelectedId(node.id)
                graphRef.current?.centerAt?.(node.x || 0, node.y || 0, 650)
                graphRef.current?.zoom?.(2.1, 650)
              }}
              onNodeDragEnd={(node: GraphNode) => {
                node.fx = node.x
                node.fy = node.y
              }}
              onNodeHover={(node: GraphNode | null) => setHoveredId(node?.id || null)}
              width={width}
            />
          </div>

          <aside className="rounded-2xl border border-slate-200/70 bg-white/80 p-4 dark:border-white/10 dark:bg-black/20">
            {selectedNode ? (
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
                  Selected item
                </p>
                <h4 className="mt-2 text-base font-semibold text-slate-950 dark:text-white">
                  {selectedNode.label}
                </h4>
                <div className="mt-3 flex flex-wrap gap-2">
                  <GraphPill>{kindLabel(selectedNode.kind)}</GraphPill>
                  <GraphPill>{relatedIds.size} related</GraphPill>
                </div>
                {selectedNode.detail ? (
                  <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-zinc-400">
                    {selectedNode.detail}
                  </p>
                ) : null}
                <div className="mt-4 grid gap-2">
                  <button
                    type="button"
                    onClick={focusSelected}
                    className="rounded-xl bg-slate-950 px-3 py-2 text-xs font-medium text-white transition hover:bg-slate-800 dark:bg-white dark:text-zinc-950 dark:hover:bg-zinc-200"
                  >
                    Focus related items
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedId(null)
                      setFocusMode(false)
                    }}
                    className="rounded-xl border border-slate-200/70 bg-white/70 px-3 py-2 text-xs font-medium text-slate-600 transition hover:bg-white dark:border-white/10 dark:bg-white/[0.05] dark:text-zinc-300 dark:hover:bg-white/10"
                  >
                    Clear selection
                  </button>
                </div>
              </div>
            ) : (
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500 dark:text-zinc-500">
                  Inspector
                </p>
                <h4 className="mt-2 text-base font-semibold text-slate-950 dark:text-white">
                  Click any item
                </h4>
                <p className="mt-3 text-sm leading-6 text-slate-500 dark:text-zinc-400">
                  Select a memory, tag, person/topic, category, or date to inspect details and focus related items.
                </p>
              </div>
            )}
          </aside>
        </div>
      )}

      <div className="mt-3 flex flex-wrap gap-2 text-[11px] text-slate-500 dark:text-zinc-500">
        <span>Drag items.</span>
        <span>Scroll or pinch to zoom.</span>
        <span>Click an item to inspect.</span>
        <span>Focus item shows connected memories and topics.</span>
      </div>
    </div>
  )
}


function indexRelationshipLabel(kind: NodeKind) {
  if (kind === "type") return "Category relationship"
  if (kind === "tag") return "Tag relationship"
  if (kind === "entity") return "People/topic relationship"
  if (kind === "timeline") return "Date relationship"
  return "Memory relationship"
}

function kindLabel(kind: NodeKind) {
  if (kind === "note") return "Memory"
  if (kind === "type") return "Category"
  if (kind === "tag") return "Tag"
  if (kind === "entity") return "People & topics"
  if (kind === "timeline") return "Date"
  return "Item"
}

function emptyGraph(): BuiltGraph {
  return { nodes: [], links: [], nodeById: new Map() }
}

function buildGraph(payload: MemoryGraphCanvasPayload, query: string, sectionFilter: GraphSectionFilter): BuiltGraph {
  const allNodes = new Map<string, GraphNode>()
  const allLinks: GraphLink[] = []
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
            allLinks.push({
              source: resource.id,
              target: `note:${rawNoteId}`,
              kind: "index",
              label: indexRelationshipLabel(resource.kind),
            })
          })
      })
  }

  if (showAll || sectionFilter === "candidate_backlinks") {
    items(payload, "candidate_backlinks")
      .slice(0, MAX_LINKS)
      .forEach((link) => {
        const sourceRawId = text(link, "source_note_id")
        const targetRawId = text(link, "target_note_id")
        const sourceNote = notesByRawId.get(sourceRawId)
        const targetNote = notesByRawId.get(targetRawId)
        if (!sourceRawId || !targetRawId || !sourceNote || !targetNote) return

        addNoteNode(allNodes, sourceRawId, sourceNote)
        addNoteNode(allNodes, targetRawId, targetNote)
        allLinks.push({
          source: `note:${sourceRawId}`,
          target: `note:${targetRawId}`,
          kind: "backlink",
          label: "Suggested relationship",
        })
      })
  }

  const q = query.trim().toLowerCase()
  const visibleIds = new Set<string>()

  for (const node of allNodes.values()) {
    if (!q || node.searchText.includes(q)) visibleIds.add(node.id)
  }

  if (q) {
    for (const link of allLinks) {
      const sourceId = endpointId(link.source)
      const targetId = endpointId(link.target)
      if (visibleIds.has(sourceId) || visibleIds.has(targetId)) {
        visibleIds.add(sourceId)
        visibleIds.add(targetId)
      }
    }
  }

  const nodes = Array.from(allNodes.values()).filter((node) => visibleIds.has(node.id))
  const nodeIds = new Set(nodes.map((node) => node.id))
  const links = dedupeLinks(allLinks)
    .filter((link) => nodeIds.has(endpointId(link.source)) && nodeIds.has(endpointId(link.target)))
    .slice(0, MAX_LINKS)

  return {
    nodes,
    links,
    nodeById: new Map(nodes.map((node) => [node.id, node])),
  }
}

function addNoteNode(nodes: Map<string, GraphNode>, rawId: string, note: GraphRecord) {
  const id = `note:${rawId}`
  if (nodes.has(id)) return

  const label = text(note, "title") || text(note, "body_preview") || "Untitled note"
  const detail = [text(note, "note_type"), ids(note, "tags").slice(0, 3).join(", ")]
    .filter(Boolean)
    .join(" · ")

  nodes.set(id, {
    id,
    rawId,
    kind: "note",
    label,
    detail,
    searchText: [rawId, label, detail, text(note, "body_preview")].join(" ").toLowerCase(),
    val: 5,
    group: "note",
  })
}

function resourceNode(section: GraphSectionKey, item: GraphRecord): GraphNode | null {
  if (section === "types") {
    const value = text(item, "type") || "unknown"
    return makeResourceNode(`type:${value}`, value, "type", `${text(item, "count")} memories`, item)
  }

  if (section === "tags") {
    const value = text(item, "tag")
    if (!value) return null
    return makeResourceNode(`tag:${value}`, value, "tag", `${text(item, "count")} memories`, item)
  }

  if (section === "entities") {
    const key = text(item, "entity_key") || text(item, "entity_name")
    const label = text(item, "entity_name") || key
    if (!key || !label) return null
    return makeResourceNode(`entity:${key}`, label, "entity", text(item, "entity_type"), item)
  }

  if (section === "timeline") {
    const value = text(item, "date")
    if (!value) return null
    return makeResourceNode(`timeline:${value}`, value, "timeline", `${text(item, "count")} memories`, item)
  }

  return null
}

function makeResourceNode(id: string, label: string, kind: NodeKind, detail: string, item: GraphRecord): GraphNode {
  return {
    id,
    rawId: id,
    kind,
    label,
    detail,
    searchText: [id, label, detail, ids(item, "note_ids").join(" ")].join(" ").toLowerCase(),
    val: kind === "entity" ? 4 : 3,
    group: kind,
  }
}

function focusGraph(graph: BuiltGraph, selectedId: string, relatedIds: Set<string>): BuiltGraph {
  const allowedIds = new Set([selectedId, ...relatedIds])
  const nodes = graph.nodes.filter((node) => allowedIds.has(node.id))
  const nodeIds = new Set(nodes.map((node) => node.id))
  const links = graph.links.filter((link) => nodeIds.has(endpointId(link.source)) && nodeIds.has(endpointId(link.target)))

  return {
    nodes,
    links,
    nodeById: new Map(nodes.map((node) => [node.id, node])),
  }
}

function relatedNodeIds(links: GraphLink[], selectedId: string | null) {
  const out = new Set<string>()
  if (!selectedId) return out

  for (const link of links) {
    const sourceId = endpointId(link.source)
    const targetId = endpointId(link.target)

    if (sourceId === selectedId) out.add(targetId)
    if (targetId === selectedId) out.add(sourceId)
  }

  return out
}

function dedupeLinks(links: GraphLink[]) {
  const seen = new Set<string>()
  const out: GraphLink[] = []

  for (const link of links) {
    const sourceId = endpointId(link.source)
    const targetId = endpointId(link.target)
    const key = `${sourceId}->${targetId}->${link.kind}`

    if (seen.has(key)) continue
    seen.add(key)
    out.push(link)
  }

  return out
}

function endpointId(value: string | GraphNode) {
  return typeof value === "string" ? value : value.id
}

function drawNode(
  node: GraphNode,
  canvasContext: CanvasRenderingContext2D,
  globalScale: number,
  selectedId: string | null,
  hoveredId: string | null,
  relatedIds: Set<string>,
) {
  const selected = selectedId === node.id
  const hovered = hoveredId === node.id
  const related = relatedIds.has(node.id)
  const dimmed = Boolean(selectedId) && !selected && !related
  const radius = node.kind === "note" ? 6.5 + node.val : 5.5 + node.val
  const fontSize = selected || hovered ? 13 : 11
  const label = truncate(node.label, selected || hovered ? 34 : 20)
  const x = node.x || 0
  const y = node.y || 0

  canvasContext.save()
  canvasContext.globalAlpha = dimmed ? 0.28 : 1

  canvasContext.beginPath()
  canvasContext.arc(x, y, selected || hovered ? radius + 3 : radius, 0, Math.PI * 2)
  canvasContext.fillStyle = nodeFill(node.kind, selected, hovered)
  canvasContext.fill()
  canvasContext.lineWidth = selected ? 3 : hovered || related ? 2.2 : 1.4
  canvasContext.strokeStyle = nodeStroke(node.kind, selected, hovered, related)
  canvasContext.stroke()

  if (selected || hovered || globalScale > 0.72) {
    canvasContext.font = `${Math.max(fontSize / globalScale, 8)}px Inter, ui-sans-serif, system-ui`
    canvasContext.textAlign = "center"
    canvasContext.textBaseline = "top"
    canvasContext.lineWidth = 4 / globalScale
    canvasContext.strokeStyle = "rgba(255,255,255,0.9)"
    canvasContext.strokeText(label, x, y + radius + 5)
    canvasContext.fillStyle = "rgba(15,23,42,0.94)"
    canvasContext.fillText(label, x, y + radius + 5)
  }

  canvasContext.restore()
}

function nodeFill(kind: NodeKind, selected: boolean, hovered: boolean) {
  if (selected) return "rgba(34, 211, 238, 0.95)"
  if (hovered) return "rgba(125, 211, 252, 0.95)"
  if (kind === "note") return "rgba(255, 255, 255, 0.98)"
  if (kind === "entity") return "rgba(245, 243, 255, 0.98)"
  if (kind === "timeline") return "rgba(254, 243, 199, 0.98)"
  if (kind === "tag") return "rgba(209, 250, 229, 0.98)"
  return "rgba(241, 245, 249, 0.98)"
}

function nodeStroke(kind: NodeKind, selected: boolean, hovered: boolean, related: boolean) {
  if (selected) return "rgba(8, 145, 178, 1)"
  if (hovered || related) return "rgba(14, 165, 233, 0.95)"
  if (kind === "note") return "rgba(34, 211, 238, 0.85)"
  if (kind === "entity") return "rgba(167, 139, 250, 0.8)"
  if (kind === "timeline") return "rgba(245, 158, 11, 0.78)"
  if (kind === "tag") return "rgba(16, 185, 129, 0.78)"
  return "rgba(148, 163, 184, 0.75)"
}

function linkColor(link: GraphLink, selectedId: string | null, hoveredId: string | null, relatedIds: Set<string>) {
  if (isHighlightedLink(link, selectedId, hoveredId, relatedIds)) return "rgba(14, 165, 233, 0.92)"
  return link.kind === "backlink" ? "rgba(100,116,139,0.33)" : "rgba(148,163,184,0.24)"
}

function isHighlightedLink(link: GraphLink, selectedId: string | null, hoveredId: string | null, relatedIds: Set<string>) {
  const sourceId = endpointId(link.source)
  const targetId = endpointId(link.target)
  const activeId = hoveredId || selectedId

  if (!activeId) return false
  if (sourceId === activeId || targetId === activeId) return true
  return relatedIds.has(sourceId) || relatedIds.has(targetId)
}

function GraphPill({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full border border-slate-200/70 bg-white/70 px-2.5 py-1 text-xs text-slate-500 dark:border-white/10 dark:bg-white/[0.05] dark:text-zinc-400">
      {children}
    </span>
  )
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
