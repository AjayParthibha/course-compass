import type { Placement } from '../../api/types'
import { termLabel } from '../../ui/terms'

export type CardState = 'completed' | 'in_progress' | 'planned' | 'open' | 'ghost'

export const cardState = (p: Placement): CardState => (p.course ? p.status : 'open')

const stateLabel: Record<CardState, string> = {
  completed: 'completed',
  in_progress: 'in progress',
  planned: 'planned',
  open: 'not chosen yet',
  ghost: 'previous position',
}

export function nodeLabel(p: Placement, state: CardState, problem: boolean, moved = false) {
  const parts = p.course
    ? [p.course, p.title, termLabel(p.term, true), stateLabel[state]]
    : ['Open slot', p.slot_label, termLabel(p.term, true), `${p.credits} credits`]
  if (p.locked) parts.push(`kept in ${termLabel(p.term, true)}`)
  if (moved) parts.push('moved here by the proposal')
  if (problem) parts.push('has a problem')
  return parts.filter(Boolean).join(', ')
}
