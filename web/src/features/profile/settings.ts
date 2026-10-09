export const CREDIT_MIN = 12
export const CREDIT_MAX = 23
// how far ahead graduation can be set, in terms (matches the backend)
export const TERMS_AHEAD = 8

export function nextTerm(term: string) {
  const year = Number(term.slice(2))
  return term.startsWith('FA') ? `SP${String(year + 1).padStart(2, '0')}` : `FA${term.slice(2)}`
}

export const termIndex = (term: string) => Number(term.slice(2)) * 2 + (term.startsWith('FA') ? 1 : 0)

/** Terms after `current`, up to and including `last` (or `count` terms when no `last`). */
export function termsAfter(current: string, last?: string, count = TERMS_AHEAD) {
  const out: string[] = []
  let t = current
  while (out.length < count && (!last || termIndex(t) < termIndex(last))) {
    t = nextTerm(t)
    out.push(t)
  }
  return out
}

/** Error text for a credit field, or null. Blank is fine unless `required`. */
export function creditError(value: string, required = false) {
  if (!value.trim()) return required ? 'Enter a number of credits.' : null
  const n = Number(value)
  if (!Number.isInteger(n)) return 'Use a whole number of credits.'
  if (n < CREDIT_MIN || n > CREDIT_MAX) return `Pick between ${CREDIT_MIN} and ${CREDIT_MAX} credits.`
  return null
}

/** Caps worth saving: only the remaining terms, blanks dropped. */
export function capsToSave(caps: Record<string, string>, remaining: string[]) {
  return Object.fromEntries(remaining.filter((t) => caps[t]?.trim()).map((t) => [t, Number(caps[t])]))
}
