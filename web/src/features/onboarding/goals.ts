import type { components } from '../../api/schema'

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
