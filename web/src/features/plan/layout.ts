import type { AuditResult, Placement, PlanEdge, RequirementStatus } from '../../api/types'

export const NODE_W = 110
export const NODE_H = 56
export const COL_W = 122
export const ROW_H = 66
export const LEFT = 16
export const TOP = 52

export type Pos = { x: number; y: number; col: number; row: number }

/** Index of the top-level requirement each placement counts toward. */
export function lanes(audit: AuditResult): Map<string, number> {
  const out = new Map<string, number>()
  const visit = (req: RequirementStatus, lane: number) => {
    for (const id of req.filled) if (!out.has(id)) out.set(id, lane)
    req.children.forEach((c) => visit(c, lane))
  }
  audit.requirements.forEach((r, i) => visit(r, i))
  return out
}

/** Terms are columns; inside a column, courses stack by requirement so related ones line up. */
export function layoutPlan(placements: Placement[], terms: string[], audit: AuditResult) {
  const lane = lanes(audit)
  const positions = new Map<string, Pos>()
  let maxRows = 0
  terms.forEach((term, col) => {
    const inTerm = placements
      .filter((p) => p.term === term)
      .sort(
        (a, b) =>
          (lane.get(a.id) ?? 99) - (lane.get(b.id) ?? 99) ||
          (a.course ?? '~').localeCompare(b.course ?? '~'),
      )
    inTerm.forEach((p, row) => {
      positions.set(p.id, { x: LEFT + col * COL_W, y: TOP + row * ROW_H, col, row })
    })
    maxRows = Math.max(maxRows, inTerm.length)
  })
  return { positions, height: TOP + maxRows * ROW_H + 8, width: LEFT + terms.length * COL_W }
}

export function columnAt(x: number, count: number) {
  const col = Math.round((x - LEFT) / COL_W)
  return Math.min(Math.max(col, 0), count - 1)
}

/** Everything upstream (prereqs) and downstream (unlocks) of a placement. */
export function chain(id: string, edges: PlanEdge[]) {
  const up = new Set<string>([id])
  const down = new Set<string>([id])
  const walk = (set: Set<string>, from: 'source' | 'target', to: 'source' | 'target') => {
    let grew = true
    while (grew) {
      grew = false
      for (const e of edges) {
        if (set.has(e[to]) && !set.has(e[from])) {
          set.add(e[from])
          grew = true
        }
      }
    }
  }
  walk(up, 'source', 'target')
  walk(down, 'target', 'source')
  return { up, down }
}
