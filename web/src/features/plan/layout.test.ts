import { describe, expect, it } from 'vitest'
import type { AuditResult, Placement } from '../../api/types'
import { COL_W, LEFT, chain, columnAt, graphWidth, initialScrollX, layoutPlan } from './layout'

const p = (id: string, term: string, course: string): Placement => ({
  id, term, course, title: null, slot: null, slot_label: null, credits: 4, status: 'planned', locked: false, origin: 'user',
})

const audit: AuditResult = {
  complete: false,
  unassigned: [],
  requirements: [
    { id: 'core', label: 'Core', status: 'planned', needed: 2, filled: ['b'], open_slots: 0, children: [] },
    { id: 'intro', label: 'Intro', status: 'done', needed: 1, filled: ['a'], open_slots: 0, children: [] },
  ],
}

describe('layoutPlan', () => {
  it('puts terms in columns and orders rows by requirement', () => {
    const { positions } = layoutPlan([p('a', 'FA24', 'CS 1110'), p('b', 'FA24', 'CS 2800')], ['FA24', 'SP25'], audit)
    expect(positions.get('b')).toMatchObject({ col: 0, row: 0 })
    expect(positions.get('a')).toMatchObject({ col: 0, row: 1 })
  })

  it('snaps x to the nearest column', () => {
    expect(columnAt(LEFT + COL_W * 2 + 40, 8)).toBe(2)
    expect(columnAt(-500, 8)).toBe(0)
    expect(columnAt(5000, 8)).toBe(7)
  })
})

describe('initialScrollX', () => {
  it('does not pan when every term fits', () => {
    expect(initialScrollX(8, 4, graphWidth(8))).toBe(0)
  })

  it('pans so the current term is near the left edge', () => {
    const x = initialScrollX(8, 4, 500)
    expect(LEFT + 4 * COL_W - x).toBe(24)
  })

  it('never pans past the last term', () => {
    const width = graphWidth(8) - 100
    expect(initialScrollX(8, 6, width)).toBe(100)
  })

  it('stays at the start when the current term is the first one', () => {
    expect(initialScrollX(8, 0, 300)).toBe(0)
    expect(initialScrollX(8, -1, 300)).toBe(0)
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
