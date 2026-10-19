import type { components } from '../../api/schema'
import { termIndex, termsAfter } from '../profile/settings'

type FactCreate = Pick<components['schemas']['FactCreate'], 'dimension' | 'value' | 'text'>

export const AFTER = [
  { id: 'industry', label: 'A job in industry' },
  { id: 'grad_school', label: 'Grad school' },
  { id: 'undecided', label: 'Not sure yet' },
  { id: 'other', label: 'Something else' },
] as const

export const INTERESTS = [
  { id: 'ml', label: 'Machine learning', phrase: 'machine learning' },
  { id: 'systems', label: 'Systems', phrase: 'systems' },
  { id: 'theory', label: 'Theory', phrase: 'theory' },
  { id: 'security', label: 'Security', phrase: 'security' },
  { id: 'hci', label: 'HCI', phrase: 'human-computer interaction' },
  { id: 'pl', label: 'Programming languages', phrase: 'programming languages' },
  { id: 'graphics', label: 'Graphics', phrase: 'graphics' },
  { id: 'data', label: 'Data science', phrase: 'data science' },
] as const

export const LOADS = [
  { id: 'light', label: 'Lighter', credits: 15, text: 'Prefers lighter semesters, about 15 credits' },
  { id: 'typical', label: 'Typical', credits: 18, text: 'Fine with typical semesters, up to 18 credits' },
  { id: 'heavy', label: 'Heavier', credits: 21, text: 'Happy to take heavier semesters, up to 21 credits' },
] as const

export type After = (typeof AFTER)[number]['id']
export type Load = (typeof LOADS)[number]['id']

export interface Goals {
  after: After | null
  afterOther: string
  interests: string[]
  interestOther: string
  load: Load | null
}

export const emptyGoals: Goals = { after: null, afterOther: '', interests: [], interestOther: '', load: null }

/** Profile facts (all "stated") for whatever the student answered. */
export function goalFacts(g: Goals): FactCreate[] {
  const facts: FactCreate[] = []
  const other = g.afterOther.trim()
  if (g.after === 'industry')
    facts.push({ dimension: 'career_track', value: 'industry', text: 'Plans to work in industry after graduating' })
  if (g.after === 'grad_school')
    facts.push({ dimension: 'grad_school', value: 'yes', text: 'Planning on grad school after graduating' })
  if (g.after === 'undecided')
    facts.push({ dimension: 'career_track', value: 'undecided', text: 'Hasn’t decided what comes after graduating' })
  if (g.after === 'other' && other)
    facts.push({ dimension: 'career_track', value: other, text: `After graduating: ${other}` })
  for (const i of INTERESTS)
    if (g.interests.includes(i.id)) facts.push({ dimension: 'interest', value: i.id, text: `Interested in ${i.phrase}` })
  const extra = g.interestOther.trim()
  if (extra) facts.push({ dimension: 'interest', value: extra, text: `Interested in ${extra}` })
  const load = LOADS.find((l) => l.id === g.load)
  if (load) facts.push({ dimension: 'term_load', value: load.id, text: load.text })
  return facts
}

type ExistingFact = Pick<components['schemas']['ProfileFact'], 'id' | 'dimension' | 'value' | 'status'>

// answers that replace earlier ones instead of adding to them
const SINGLE_VALUED = [['term_load'], ['career_track', 'grad_school']]

/** Ids of earlier facts that the new answers contradict, to mark superseded before saving. */
export function factsToSupersede(existing: ExistingFact[], next: FactCreate[]): number[] {
  const keep = new Set(next.map((f) => `${f.dimension}:${f.value}`))
  const groups = SINGLE_VALUED.filter((dims) => next.some((f) => dims.includes(f.dimension)))
  return existing
    .filter(
      (f) =>
        f.status !== 'superseded' &&
        f.status !== 'rejected' &&
        groups.some((dims) => dims.includes(f.dimension)) &&
        !keep.has(`${f.dimension}:${f.value}`),
    )
    .map((f) => f.id)
}

type Setup = { program?: string | null; entering_term?: string | null; graduation_term?: string | null }

/** Start from what the student already set up, so re-running onboarding doesn't reset it. */
export function startingChoices(me: Setup | undefined, programs: string[]) {
  return {
    program: me?.program && programs.includes(me.program) ? me.program : programs[0],
    entering: me?.entering_term ?? 'FA24',
    graduating: me?.graduation_term ?? 'SP28',
  }
}

/**
 * Where a student is, from their first semester and the current one: starting next term
 * (nothing taken yet), in their first semester (taking courses now), or partway through.
 */
export type Stage = 'incoming' | 'first' | 'continuing'

export function stageOf(entering: string, current: string): Stage {
  const e = termIndex(entering)
  const c = termIndex(current)
  return e > c ? 'incoming' : e === c ? 'first' : 'continuing'
}

/** FA24 -> 2024-25, SP25 -> 2024-25 (as the backend reads it). */
export function catalogYear(entering: string) {
  const year = 2000 + Number(entering.slice(2))
  const start = entering.startsWith('FA') ? year : year - 1
  return `${start}-${String(start + 1).slice(2)}`
}

/** The rule year a student is checked against when it isn't their entering year's
 * (later entrants share the newest rules we have), else null. */
export function olderRules(entering: string, years: string[]) {
  const wanted = catalogYear(entering)
  const used = years.filter((y) => y <= wanted).sort().at(-1)
  return used && used !== wanted ? used : null
}

/** Graduation choices: from this term (or the term after the first one) for five years. */
export function graduationTerms(entering: string, current: string) {
  return stageOf(entering, current) === 'continuing'
    ? [current, ...termsAfter(current, undefined, 9)]
    : termsAfter(termIndex(entering) > termIndex(current) ? entering : current, undefined, 10)
}
