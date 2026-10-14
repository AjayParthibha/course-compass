import type { Course, Placement } from '../../api/types'

export type PrereqExpr = NonNullable<Course['prereqs']>

export type CourseState = 'done' | 'in_progress' | 'planned' | 'late' | 'missing'

export type CourseCheck = {
  kind: 'course'
  code: string
  concurrent: boolean
  state: CourseState
  placement: Placement | null
  /** set when an equivalent or cross-listed course in the plan stands in for `code` */
  via: string | null
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
    // same rule as the backend validator: a course also counts for its cross-listings and equivalents
    const code = norm(expr.code)
    const counts = (p: Placement) =>
      !!p.course && (norm(p.course) === code || (p.counts_as ?? []).some((c) => norm(c) === code))
    const matches = placements
      .filter((p) => p.id !== target.id && counts(p))
      .sort((a, b) => at(a) - at(b) || Number(norm(b.course!) === code) - Number(norm(a.course!) === code))
    const ok = matches.find(
      (p) => p.status === 'completed' || at(p) < targetAt || (concurrent && at(p) === targetAt),
    )
    const via = (p: Placement | null) => (p?.course && norm(p.course) !== code ? p.course : null)
    if (ok) {
      const state = ok.status === 'completed' ? 'done' : ok.status === 'in_progress' ? 'in_progress' : 'planned'
      return { kind: 'course', code: expr.code, concurrent, state, placement: ok, via: via(ok), met: true }
    }
    const later = matches[0] ?? null
    return {
      kind: 'course',
      code: expr.code,
      concurrent,
      state: later ? 'late' : 'missing',
      placement: later,
      via: via(later),
      met: false,
    }
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
