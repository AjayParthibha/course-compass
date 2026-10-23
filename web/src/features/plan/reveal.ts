import type { Placement, PlanState } from '../../api/types'
import { layoutPlan } from './layout'

/**
 * What a proposal changes, in the order the preview shows it landing: term by term, top to bottom.
 * A placement changes when it is new, moves term, or gets a different course (a filled slot);
 * one that is gone comes last in the term it leaves.
 */
export function proposalChanges(before: PlanState, after: PlanState): string[] {
  const old = new Map(before.plan.placements.map((p) => [p.id, p]))
  const kept = new Set(after.plan.placements.map((p) => p.id))
  const changed = (p: Placement) => {
    const was = old.get(p.id)
    return !was || was.term !== p.term || was.course !== p.course
  }
  const gone = before.plan.placements.filter((p) => !kept.has(p.id))
  const cols = layoutPlan(after.plan.placements, after.plan.terms, after.audit)
  return after.plan.terms.flatMap((term, i) => [
    ...cols[i].filter(changed).map((p) => p.id),
    ...gone.filter((p) => p.term === term).map((p) => p.id),
  ])
}

/**
 * The plan partway through the reveal: the first `step` changes have landed, the rest are as
 * they were. Lines and problems touching a change still to come stay hidden until it lands.
 */
export function revealFrame(before: PlanState, after: PlanState, changes: string[], step: number) {
  const landed = new Set(changes.slice(0, step))
  const waiting = new Set(changes.slice(step))
  const next = new Map(after.plan.placements.map((p) => [p.id, p]))
  const placements = [
    ...before.plan.placements.flatMap((p) => (landed.has(p.id) ? (next.has(p.id) ? [next.get(p.id)!] : []) : [p])),
    ...after.plan.placements.filter((p) => landed.has(p.id) && !before.plan.placements.some((b) => b.id === p.id)),
  ]
  const state: PlanState = {
    ...after,
    plan: { ...after.plan, placements },
    edges: after.edges.filter((e) => !waiting.has(e.source) && !waiting.has(e.target)),
    violations: after.violations.filter((v) => !v.placement_ids.some((id) => waiting.has(id))),
  }
  const moved = new Set([...landed].filter((id) => next.has(id)))
  // a course that moved term leaves an outline where it was
  const ghosts = before.plan.placements.filter((p) => moved.has(p.id) && next.get(p.id)!.term !== p.term)
  return { state, moved, ghosts }
}
