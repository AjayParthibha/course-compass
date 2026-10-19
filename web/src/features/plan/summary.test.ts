import { describe, expect, it } from 'vitest'
import type { AuditResult, RequirementStatus } from '../../api/types'
import { summarizeRequirements } from './summary'

const req = (id: string, status: RequirementStatus['status'], open_slots = 0): RequirementStatus => ({
  id, label: id, status, needed: 1, filled: [], open_slots, children: [], credits: null, credits_needed: null,
})

describe('summarizeRequirements', () => {
  it('counts done, planned, open slots and requirements to confirm', () => {
    const audit: AuditResult = {
      complete: false,
      unassigned: [],
      requirements: [
        req('a', 'done'), req('b', 'done'), req('c', 'planned'), req('d', 'planned', 2),
        req('e', 'missing'), req('f', 'flagged'),
      ],
    }
    const s = summarizeRequirements(audit)
    expect(s.headline).toBe('4 of 6 requirements on track')
    expect(s.missing).toBe(1)
    expect(s.details).toEqual(['2 met', '2 planned', '2 slots to fill', '1 to confirm'])
  })

  it('counts flagged requirements as ones to confirm, not problems', () => {
    const audit: AuditResult = { complete: true, unassigned: [], requirements: [req('f', 'flagged')] }
    expect(summarizeRequirements(audit).details).toEqual(['1 to confirm'])
    expect(summarizeRequirements(audit, 2).details).toEqual(['1 to confirm', '2 plan problems'])
  })

  it('leaves out empty categories', () => {
    const s = summarizeRequirements({ complete: true, unassigned: [], requirements: [req('a', 'done')] })
    expect(s.headline).toBe('All requirements on track')
    expect(s.details).toEqual(['1 met'])
  })
})
