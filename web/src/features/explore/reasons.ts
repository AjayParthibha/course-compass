import type { Area, Candidate } from '../../api/types'

type Reason = Candidate['reasons'][number]

/** How a reason is tagged: what the student said (with its date), the plan, or a guess. */
export function basisLabel(r: Reason): { kind: 'said' | 'plan' | 'guess'; text: string } {
  if (r.basis === 'stated') return { kind: 'said', text: `You said${r.date ? ` · ${r.date}` : ''}` }
  if (r.basis === 'plan') return { kind: 'plan', text: 'Your plan' }
  return { kind: 'guess', text: 'My guess · not confirmed' }
}

/** The line above the area list: name interests only when they shaped the order. */
export function areaHint(areas: Pick<Area, 'reasons'>[]): string {
  return areas.some((a) => a.reasons.length > 0)
    ? 'Areas you’ve said you’re interested in, and ones that build on your plan, come first.'
    : 'Areas that build on your plan come first.'
}
