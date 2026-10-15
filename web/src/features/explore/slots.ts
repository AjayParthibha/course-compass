import type { Placement, PlanState } from '../../api/types'

export const slotHref = (p: Placement) => `/explore/${p.slot}?term=${p.term}&placement=${p.id}`

export function openSlots(state: PlanState): Placement[] {
  const order = state.plan.terms
  return state.plan.placements
    .filter((p) => p.slot && !p.course)
    .sort((a, b) => order.indexOf(a.term) - order.indexOf(b.term))
}
