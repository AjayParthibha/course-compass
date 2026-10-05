import { describe, expect, it } from 'vitest'
import type { AuditResult, Placement } from '../../api/types'
import { chain, columnAt, layoutPlan } from './layout'

const p = (id: string, term: string, course: string): Placement => ({
  id, term, course, title: null, slot: null, slot_label: null, credits: 4, status: 'planned', locked: false, origin: 'user',
})

const audit: AuditResult = {
  complete: false,
  unassigned: [],
  requirements: [
    { id: 'core', label: 'Core', status: 'planned', needed: 2, filled: ['b'], children: [] },
    { id: 'intro', label: 'Intro', status: 'done', needed: 1, filled: ['a'], children: [] },
  ],
}

describe('layoutPlan', () => {
  it('puts terms in columns and orders rows by requirement', () => {
    const { positions } = layoutPlan([p('a', 'FA24', 'CS 1110'), p('b', 'FA24', 'CS 2800')], ['FA24', 'SP25'], audit)
    expect(positions.get('b')).toMatchObject({ col: 0, row: 0 })
    expect(positions.get('a')).toMatchObject({ col: 0, row: 1 })
  })

  it('snaps x to the nearest column', () => {
    expect(columnAt(16 + 122 * 2 + 40, 8)).toBe(2)
    expect(columnAt(-500, 8)).toBe(0)
    expect(columnAt(5000, 8)).toBe(7)
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
