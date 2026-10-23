import { describe, expect, it } from 'vitest'
import type { Placement, PlanState } from '../../api/types'
import { proposalChanges, revealFrame } from './reveal'

const p = (id: string, term: string, course: string | null): Placement => ({
  id, term, course, title: null, slot: null, slot_label: course ? null : 'Elective', credits: 4, status: 'planned',
  locked: false, origin: 'user', counts_as: [],
})

const state = (placements: Placement[], edges: [string, string][] = []): PlanState =>
  ({
    plan: { id: 1, version: 1, terms: ['FA26', 'SP27'], current_term: 'FA26', placements },
    audit: { complete: false, unassigned: [], requirements: [] },
    edges: edges.map(([source, target]) => ({ source, target })),
    violations: [],
  }) as unknown as PlanState

// Spring gets its open slot filled and a new course; CS 3110 moves to spring; CS 1110 goes
const before = state([p('a', 'FA26', 'CS 1110'), p('b', 'FA26', 'CS 3110'), p('s', 'SP27', null)])
const after = state(
  [p('b', 'SP27', 'CS 3110'), p('s', 'SP27', 'CS 4820'), p('n', 'SP27', 'CS 4780')],
  [['b', 's']],
)

describe('proposalChanges', () => {
  it('lists moved, filled, added and removed placements term by term', () => {
    expect(proposalChanges(before, after)).toEqual(['a', 'b', 'n', 's'])
  })

  it('leaves out placements that stay the same', () => {
    expect(proposalChanges(before, before)).toEqual([])
  })
})

describe('revealFrame', () => {
  const changes = proposalChanges(before, after)

  it('starts from the current plan with no lines to changes still to come', () => {
    const { state: s, moved, ghosts } = revealFrame(before, after, changes, 0)
    expect(s.plan.placements.map((x) => `${x.id}:${x.term}:${x.course}`)).toEqual([
      'a:FA26:CS 1110',
      'b:FA26:CS 3110',
      's:SP27:null',
    ])
    expect(s.edges).toEqual([])
    expect(moved.size).toBe(0)
    expect(ghosts).toEqual([])
  })

  it('lands changes one at a time', () => {
    const { state: s, moved, ghosts } = revealFrame(before, after, changes, 2)
    expect(s.plan.placements.map((x) => `${x.id}:${x.term}`)).toEqual(['b:SP27', 's:SP27'])
    expect([...moved]).toEqual(['b'])
    expect(ghosts.map((g) => `${g.id}:${g.term}`)).toEqual(['b:FA26'])
  })

  it('ends on the proposal itself', () => {
    const { state: s, moved } = revealFrame(before, after, changes, changes.length)
    expect(s.plan.placements.map((x) => x.id).sort()).toEqual(['b', 'n', 's'])
    expect(s.edges).toEqual(after.edges)
    expect([...moved].sort()).toEqual(['b', 'n', 's'])
  })
})
