import type { PlanState } from '../../api/types'
import { termLabel } from '../../ui/terms'

type Input = {
  state: PlanState | undefined
  /** placement selected in the plan, if any */
  selected?: string | null
  /** what the student has already asked in this conversation */
  asked?: string[]
  maxCredits?: number
  termCaps?: Record<string, number>
}

const FALLBACK = ['Am I on track?', 'What’s left before I graduate?', 'Which semester is my hardest?']

// "Engineering communications" reads as "engineering communications" mid-sentence; "CS core" stays
const midSentence = (label: string) => (/^[A-Z][a-z]/.test(label) ? label[0].toLowerCase() + label.slice(1) : label)

/**
 * Prompts for the chips above the message box, picked from what's true in the plan right now:
 * a problem to fix, the selected course, a requirement still missing, open slots next term, a
 * heavy term. Anything already asked is skipped, so the chips change as the conversation goes.
 */
export function suggestPrompts({ state, selected, asked = [], maxCredits = 18, termCaps = {} }: Input, limit = 3) {
  const out: string[] = []
  const seen = new Set(asked.map((a) => a.trim().toLowerCase()))
  const add = (prompt: string | null | undefined) => {
    if (prompt && !seen.has(prompt.toLowerCase())) {
      seen.add(prompt.toLowerCase())
      out.push(prompt)
    }
  }
  if (!state) {
    FALLBACK.forEach(add)
    return out.slice(0, limit)
  }

  const { plan, audit, violations } = state
  const now = plan.terms.indexOf(plan.current_term)
  const future = plan.terms.filter((_, i) => i > now)
  const byId = new Map(plan.placements.map((p) => [p.id, p]))
  const credits = (term: string) => plan.placements.filter((p) => p.term === term).reduce((n, p) => n + p.credits, 0)

  const problem = violations.find((v) => v.blocking)
  const problemTerm = problem?.placement_ids.map((id) => byId.get(id)?.term).find(Boolean)
  const pick = selected ? byId.get(selected) : undefined
  // a credit total isn't something to "take a course for"
  const missing = audit.requirements.filter((r) => r.status === 'missing' && r.credits_needed == null)
  const slotTerm = future.find((t) => plan.placements.some((p) => p.term === t && !p.course))
  const heaviest = [...future].sort((a, b) => credits(b) - credits(a))[0]
  const heavy = heaviest && credits(heaviest) >= Math.min(15, (termCaps[heaviest] ?? maxCredits) - 2)

  // one of each kind first, most pressing first, so three chips cover different ground
  if (problem) add(problemTerm ? `Fix the problem in ${termLabel(problemTerm)}` : 'Fix the problems in my plan')
  if (pick?.course) add(`Is ${pick.course} a good fit for me?`)
  else if (pick?.slot_label) add(`What fits my ${termLabel(pick.term)} ${midSentence(pick.slot_label)} slot?`)
  if (missing[0]) add(`What should I take for ${midSentence(missing[0].label)}?`)
  if (slotTerm) add(`Fill my ${termLabel(slotTerm)} open slots`)
  if (heavy) add(`Make ${termLabel(heaviest)} lighter`)
  if (pick?.course) add(`What does ${pick.course} lead to?`)
  missing.slice(1).forEach((r) => add(`What should I take for ${midSentence(r.label)}?`))
  FALLBACK.forEach(add)
  return out.slice(0, limit)
}
