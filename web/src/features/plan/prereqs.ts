import type { Course, Placement } from '../../api/types'

export type PrereqExpr = NonNullable<Course['prereqs']>

export type CourseState = 'done' | 'in_progress' | 'planned' | 'late' | 'missing'

export type CourseCheck = {
  kind: 'course'
  code: string
  concurrent: boolean
  state: CourseState
  placement: Placement | null
  met: boolean
}
export type GroupCheck = { kind: 'all' | 'any'; items: PrereqCheck[]; met: boolean | null }
export type FlagCheck = { kind: 'flag'; text: string; met: null }
export type PrereqCheck = CourseCheck | GroupCheck | FlagCheck

const norm = (code: string) => code.replace(/\s+/g, ' ').trim().toUpperCase()

/**
 * Evaluates a prerequisite tree against the plan, as seen from `target`'s term.
 * A course counts if it's completed or sits in an earlier term (the same term for
 * concurrent ones). `met` is null when the outcome hinges on a manual check (a flag).
 */
export function checkPrereqs(
  expr: PrereqExpr,
  target: Placement,
  placements: Placement[],
  terms: string[],
): PrereqCheck {
  const at = (p: Placement) => terms.indexOf(p.term)
  const targetAt = at(target)

  if (expr.kind === 'flag') return { kind: 'flag', text: expr.text, met: null }

  if (expr.kind === 'course') {
    const concurrent = expr.concurrent ?? false
    const matches = placements
      .filter((p) => p.id !== target.id && p.course && norm(p.course) === norm(expr.code))
      .sort((a, b) => at(a) - at(b))
    const ok = matches.find(
      (p) => p.status === 'completed' || at(p) < targetAt || (concurrent && at(p) === targetAt),
    )
    if (ok) {
      const state = ok.status === 'completed' ? 'done' : ok.status === 'in_progress' ? 'in_progress' : 'planned'
      return { kind: 'course', code: expr.code, concurrent, state, placement: ok, met: true }
    }
    const later = matches[0] ?? null
    return { kind: 'course', code: expr.code, concurrent, state: later ? 'late' : 'missing', placement: later, met: false }
  }

  const items = expr.items.map((e) => checkPrereqs(e, target, placements, terms))
  const known = items.map((i) => i.met).filter((m): m is boolean => m !== null)
  let met: boolean | null
  if (expr.kind === 'all') {
    met = known.includes(false) ? false : known.length < items.length ? null : true
  } else {
    met = known.includes(true) ? true : known.length < items.length ? null : false
  }
  return { kind: expr.kind, items, met }
}
