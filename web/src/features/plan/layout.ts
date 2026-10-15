import type { AuditResult, Placement, PlanEdge, RequirementStatus } from '../../api/types'

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
export function layoutPlan(placements: Placement[], terms: string[], audit: AuditResult): Placement[][] {
  const lane = lanes(audit)
  return terms.map((term) =>
    placements
      .filter((p) => p.term === term)
      .sort(
        (a, b) =>
          (lane.get(a.id) ?? 99) - (lane.get(b.id) ?? 99) ||
          (a.course ?? '~').localeCompare(b.course ?? '~'),
      ),
  )
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
