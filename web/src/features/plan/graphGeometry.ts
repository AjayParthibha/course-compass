import type { PlanEdge } from '../../api/types'

export const CARD_W = 128
export const CARD_H = 66
export const COL_GAP = 20
export const ROW_GAP = 10

/** A card's box in graph-content coordinates. */
export type Box = { x: number; y: number; w: number; h: number }

export type EdgeKind = 'forward' | 'same' | 'backward'
export type EdgeGeometry = { d: string; kind: EdgeKind; tip: { x: number; y: number; dir: 1 | -1 } }

export const edgeKey = (e: PlanEdge) => `${e.source}>${e.target}`

/** Horizontal channels between rows of cards, where long edges can run without crossing a card. */
export function gutters(boxes: Iterable<Box>, gap = ROW_GAP) {
  const tops: number[] = []
  let bottom = -Infinity
  for (const b of boxes) {
    if (!tops.some((t) => Math.abs(t - b.y) < 2)) tops.push(b.y)
    bottom = Math.max(bottom, b.y + b.h)
  }
  if (!tops.length) return []
  return [...tops.map((t) => t - gap / 2), bottom + gap / 2].sort((a, b) => a - b)
}

/** The channel a long edge should travel along: between its ends if possible, otherwise just below. */
export function pickGutter(sy: number, ty: number, lines: number[]) {
  const lo = Math.min(sy, ty)
  const hi = Math.max(sy, ty)
  const mid = (sy + ty) / 2
  const between = lines.filter((g) => g > lo && g < hi)
  const below = lines.filter((g) => g >= lo)
  const pool = between.length ? between : below.length ? below : lines
  if (!pool.length) return mid
  return pool.reduce((best, g) => {
    const d = Math.abs(g - mid) - Math.abs(best - mid)
    return d < 0 || (d === 0 && g > best) ? g : best
  })
}

/**
 * Where each edge leaves and enters its cards. Several edges on one side of a card fan out a little,
 * ordered by where the other end sits, so they don't all meet in one point.
 */
export function anchorYs(edges: PlanEdge[], boxes: Map<string, Box>, spread = 6) {
  const out = new Map<string, { sy: number; ty: number }>()
  const outgoing = new Map<string, PlanEdge[]>()
  const incoming = new Map<string, PlanEdge[]>()
  for (const e of edges) {
    if (!boxes.has(e.source) || !boxes.has(e.target)) continue
    outgoing.set(e.source, [...(outgoing.get(e.source) ?? []), e])
    incoming.set(e.target, [...(incoming.get(e.target) ?? []), e])
  }
  const cy = (id: string) => boxes.get(id)!.y + boxes.get(id)!.h / 2
  const offsets = (list: PlanEdge[], card: string, other: 'source' | 'target') => {
    const h = boxes.get(card)!.h
    const limit = h * 0.3
    const step = list.length > 1 ? Math.min(spread, (2 * limit) / (list.length - 1)) : 0
    const sorted = [...list].sort((a, b) => cy(a[other]) - cy(b[other]))
    return new Map(sorted.map((e, i) => [edgeKey(e), cy(card) + (i - (sorted.length - 1) / 2) * step]))
  }
  const starts = new Map<string, number>()
  const ends = new Map<string, number>()
  outgoing.forEach((list, id) => offsets(list, id, 'target').forEach((y, k) => starts.set(k, y)))
  incoming.forEach((list, id) => offsets(list, id, 'source').forEach((y, k) => ends.set(k, y)))
  for (const e of edges) {
    const k = edgeKey(e)
    if (starts.has(k)) out.set(k, { sy: starts.get(k)!, ty: ends.get(k)! })
  }
  return out
}

const r = (n: number) => Math.round(n * 10) / 10

/**
 * A smooth path from the right edge of a prerequisite to the left edge of the course it unlocks.
 * Neighbouring terms get a single S-curve through the gap between columns; longer jumps bend into
 * the nearest channel between rows, run along it, and bend back out, so they never hide behind cards.
 */
/**
 * `gap`: how far before the target card the arrow stops, so it lands on the card's visible
 * outline: 1px for a plain card, more when a selection or problem ring is drawn outside it.
 */
export function edgePath(
  s: Box,
  t: Box,
  sy: number,
  ty: number,
  lines: number[],
  colGap = COL_GAP,
  gap = 1,
): EdgeGeometry {
  const sameColumn = Math.abs(t.x - s.x) < s.w / 2
  if (sameColumn) {
    const x = Math.max(s.x + s.w, t.x + t.w)
    const reach = Math.min(16, colGap * 0.8)
    const tx = t.x + t.w + gap
    return {
      kind: 'same',
      d: `M${r(s.x + s.w)} ${r(sy)}C${r(x + reach)} ${r(sy)} ${r(x + reach)} ${r(ty)} ${r(tx)} ${r(ty)}`,
      tip: { x: tx, y: ty, dir: -1 },
    }
  }
  if (t.x < s.x) {
    const sx = s.x
    const tx = t.x + t.w + gap
    const k = Math.max(24, (sx - tx) / 2)
    return {
      kind: 'backward',
      d: `M${r(sx)} ${r(sy)}C${r(sx - k)} ${r(sy)} ${r(tx + k)} ${r(ty)} ${r(tx)} ${r(ty)}`,
      tip: { x: tx, y: ty, dir: -1 },
    }
  }
  const sx = s.x + s.w
  const tx = t.x - gap
  const tip = { x: tx, y: ty, dir: 1 as const }
  if (tx - sx <= colGap * 1.5 + 2) {
    const h = (tx - sx) / 2
    return { kind: 'forward', d: `M${r(sx)} ${r(sy)}C${r(sx + h)} ${r(sy)} ${r(tx - h)} ${r(ty)} ${r(tx)} ${r(ty)}`, tip }
  }
  const gy = pickGutter(sy, ty, lines)
  const a = sx + colGap
  const b = tx - colGap
  const h = colGap / 2
  return {
    kind: 'forward',
    d:
      `M${r(sx)} ${r(sy)}C${r(sx + h)} ${r(sy)} ${r(a - h)} ${r(gy)} ${r(a)} ${r(gy)}` +
      `L${r(b)} ${r(gy)}C${r(b + h)} ${r(gy)} ${r(tx - h)} ${r(ty)} ${r(tx)} ${r(ty)}`,
    tip,
  }
}

/** A small open chevron at the end of an edge, pointing into the card. */
export function tipPath({ x, y, dir }: EdgeGeometry['tip'], size = 4) {
  const bx = x - dir * size
  return `M${r(bx)} ${r(y - size * 0.8)}L${r(x)} ${r(y)}L${r(bx)} ${r(y + size * 0.8)}`
}

/**
 * Drawing order for a lit chain: prerequisites furthest from `id` draw first and flow towards it,
 * then what it unlocks draws outward. Returns a step index per edge key.
 */
export function chainSteps(id: string, edges: PlanEdge[]) {
  const depth = (from: 'source' | 'target', to: 'source' | 'target') => {
    const dist = new Map([[id, 0]])
    let frontier = [id]
    while (frontier.length) {
      const next: string[] = []
      for (const e of edges) {
        if (frontier.includes(e[to]) && !dist.has(e[from])) {
          dist.set(e[from], dist.get(e[to])! + 1)
          next.push(e[from])
        }
      }
      frontier = next
    }
    return dist
  }
  const up = depth('source', 'target')
  const down = depth('target', 'source')
  const upEdges = edges.filter((e) => up.has(e.source) && up.has(e.target) && up.get(e.source)! > up.get(e.target)!)
  const maxUp = Math.max(0, ...upEdges.map((e) => up.get(e.target)!))
  const steps = new Map<string, number>()
  for (const e of upEdges) steps.set(edgeKey(e), maxUp - up.get(e.target)!)
  const offset = upEdges.length ? maxUp + 1 : 0
  for (const e of edges) {
    if (down.has(e.source) && down.has(e.target) && down.get(e.target)! > down.get(e.source)!) {
      steps.set(edgeKey(e), offset + down.get(e.source)!)
    }
  }
  return steps
}

/** How far each card moved between two measurements; unmoved and new cards are left out. */
export function flipDeltas(prev: Map<string, Box>, next: Map<string, Box>, min = 0.5) {
  const out: { id: string; dx: number; dy: number }[] = []
  next.forEach((b, id) => {
    const a = prev.get(id)
    if (!a) return
    const dx = a.x - b.x
    const dy = a.y - b.y
    if (Math.abs(dx) > min || Math.abs(dy) > min) out.push({ id, dx, dy })
  })
  return out
}
