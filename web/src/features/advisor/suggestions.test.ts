import { describe, expect, it } from 'vitest'
import type { Placement, PlanState, RequirementStatus, Violation } from '../../api/types'
import { suggestPrompts } from './suggestions'

const TERMS = ['FA25', 'SP26', 'FA26', 'SP27', 'FA27']

const course = (id: string, term: string, credits = 4): Placement =>
  ({ id, term, course: id, credits, status: 'planned', locked: false, origin: 'user', counts_as: [] }) as unknown as Placement
const slot = (id: string, term: string, label: string): Placement =>
  ({ id, term, course: null, slot: id, slot_label: label, credits: 3, status: 'planned', locked: false, origin: 'user', counts_as: [] }) as unknown as Placement
const req = (id: string, label: string, status: RequirementStatus['status']): RequirementStatus =>
  ({ id, label, status, needed: 1, filled: [], open_slots: 0, children: [] }) as RequirementStatus

function state(placements: Placement[], requirements: RequirementStatus[] = [], violations: Violation[] = []): PlanState {
  return {
    plan: { terms: TERMS, current_term: 'FA26', placements },
    audit: { complete: false, unassigned: [], requirements },
    violations,
  } as unknown as PlanState
}

describe('suggestPrompts', () => {
  it('falls back to general questions when nothing stands out', () => {
    expect(suggestPrompts({ state: state([course('CS 1110', 'FA25')]) })).toEqual([
      'Am I on track?',
      'What’s left before I graduate?',
      'Which semester is my hardest?',
    ])
  })

  it('puts a blocking problem first and names its term', () => {
    const problem = { kind: 'prereq', message: 'x', placement_ids: ['CS 4820'], blocking: true } as Violation
    const s = state([course('CS 4820', 'SP27')], [req('comm', 'Engineering communications', 'missing')], [problem])
    expect(suggestPrompts({ state: s })).toEqual([
      'Fix the problem in Spring ’27',
      'What should I take for engineering communications?',
      'Am I on track?',
    ])
  })

  it('asks about the selected course or slot', () => {
    const s = state([course('CS 4820', 'SP27'), slot('ls', 'FA27', 'Liberal studies')])
    expect(suggestPrompts({ state: s, selected: 'CS 4820' })[0]).toBe('Is CS 4820 a good fit for me?')
    expect(suggestPrompts({ state: s, selected: 'ls' })[0]).toBe('What fits my Fall ’27 liberal studies slot?')
  })

  it('points at the next term with open slots and the heaviest future term', () => {
    const s = state([
      slot('a', 'SP27', 'Practicum'),
      course('CS 4410', 'FA27'), course('CS 4780', 'FA27'), course('CS 4820', 'FA27'), course('MATH 4710', 'FA27'),
    ])
    expect(suggestPrompts({ state: s })).toEqual(['Fill my Spring ’27 open slots', 'Make Fall ’27 lighter', 'Am I on track?'])
  })

  it('skips what was already asked so the chips move on', () => {
    const s = state([], [req('comm', 'Engineering communications', 'missing'), req('fws', 'First-year writing seminars', 'missing')])
    expect(suggestPrompts({ state: s, asked: ['What should I take for engineering communications?', 'am i on track?'] })).toEqual([
      'What should I take for first-year writing seminars?',
      'What’s left before I graduate?',
      'Which semester is my hardest?',
    ])
  })

  it('keeps acronyms in labels as written', () => {
    const s = state([], [req('e4000', '4000+ CS electives', 'missing'), req('core', 'CS core', 'missing')])
    expect(suggestPrompts({ state: s }).slice(0, 2)).toEqual([
      'What should I take for 4000+ CS electives?',
      'What should I take for CS core?',
    ])
  })
})
