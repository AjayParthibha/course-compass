import { describe, expect, it } from 'vitest'
import type { AuditResult, Placement } from '../../api/types'
import { chain, layoutPlan } from './layout'

const p = (id: string, term: string, course: string): Placement => ({
  id, term, course, title: null, slot: null, slot_label: null, credits: 4, status: 'planned', locked: false, origin: 'user',
  counts_as: [],
})

const audit: AuditResult = {
  complete: false,
  unassigned: [],
  requirements: [
    { id: 'core', label: 'Core', status: 'planned', needed: 2, filled: ['b'], open_slots: 0, children: [], credits: null, credits_needed: null },
    { id: 'intro', label: 'Intro', status: 'done', needed: 1, filled: ['a'], open_slots: 0, children: [], credits: null, credits_needed: null },
  ],
}

describe('layoutPlan', () => {
  it('puts terms in columns and orders rows by requirement', () => {
    const cols = layoutPlan(
      [p('a', 'FA24', 'CS 1110'), p('b', 'FA24', 'CS 2800'), p('c', 'SP25', 'CS 2110'), p('d', 'FA24', 'AAS 1100')],
      ['FA24', 'SP25', 'FA25'],
      audit,
    )
    expect(cols.map((col) => col.map((x) => x.id))).toEqual([['b', 'a', 'd'], ['c'], []])
  })
})

describe('chain', () => {
  it('walks prerequisites and unlocks transitively', () => {
    const edges = [
      { source: 'a', target: 'b' },
      { source: 'b', target: 'c' },
      { source: 'x', target: 'y' },
    ]
    const { up, down } = chain('b', edges)
    expect([...up].sort()).toEqual(['a', 'b'])
    expect([...down].sort()).toEqual(['b', 'c'])
  })
})
