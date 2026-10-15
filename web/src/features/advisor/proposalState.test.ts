import { describe, expect, it } from 'vitest'
import type { AdvisorEvent, Proposal, Violation } from '../../api/types'
import { isOutdated, latestProposalId, proposalCardState } from './proposalState'

const blocking: Violation = { kind: 'prereq', message: 'CS 3110 needs CS 2110 first', placement_ids: [], blocking: true }

function proposal(id: number, extra: Partial<Proposal> = {}): Proposal {
  return {
    id,
    plan_id: 1,
    base_version: 4,
    summary: 'Move CS 4780',
    ops: [],
    changes: [],
    rejected: [],
    checks: [],
    violations: [],
    status: 'pending',
    created_at: '2026-10-01T00:00:00Z',
    ...extra,
  }
}

describe('proposalCardState', () => {
  it('offers the newest pending proposal for the current plan', () => {
    expect(proposalCardState(proposal(2), 4, 2)).toBe('ready')
    expect(proposalCardState(proposal(2), undefined, 2)).toBe('ready')
  })

  it('reports applied and discarded proposals as such', () => {
    expect(proposalCardState(proposal(1, { status: 'applied' }), 5, 2)).toBe('applied')
    expect(proposalCardState(proposal(1, { status: 'discarded' }), 4, 2)).toBe('discarded')
  })

  it('flags proposals that failed the planner check', () => {
    expect(proposalCardState(proposal(3, { violations: [blocking] }), 4, 2)).toBe('blocked')
  })

  it('marks older pending proposals as replaced', () => {
    expect(proposalCardState(proposal(1), 4, 2)).toBe('replaced')
  })

  it('marks proposals made against an older plan as outdated', () => {
    expect(proposalCardState(proposal(2), 5, 2)).toBe('outdated')
    expect(proposalCardState(proposal(2, { status: 'outdated' }), undefined, 2)).toBe('outdated')
    expect(isOutdated(proposal(1), 5)).toBe(true)
    expect(isOutdated(proposal(1, { status: 'applied' }), 5)).toBe(false)
  })
})

describe('latestProposalId', () => {
  it('ignores proposals that failed the planner check', () => {
    const events: AdvisorEvent[] = [
      { type: 'proposal', proposal: proposal(1) },
      { type: 'text', delta: 'hi' },
      { type: 'proposal', proposal: proposal(2, { violations: [blocking] }) },
    ]
    expect(latestProposalId(events)).toBe(1)
    expect(latestProposalId([])).toBeNull()
  })
})
