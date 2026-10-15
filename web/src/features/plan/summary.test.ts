import { describe, expect, it } from 'vitest'
import type { AuditResult, RequirementStatus } from '../../api/types'
import { summarizeRequirements } from './summary'

const req = (id: string, status: RequirementStatus['status'], open_slots = 0): RequirementStatus => ({
  id, label: id, status, needed: 1, filled: [], open_slots, children: [],
})

describe('summarizeRequirements', () => {
  it('counts done, planned, open slots and requirements needing attention', () => {
    const audit: AuditResult = {
      complete: false,
      unassigned: [],
      requirements: [
        req('a', 'done'), req('b', 'done'), req('c', 'planned'), req('d', 'planned', 2),
        req('e', 'missing'), req('f', 'flagged'),
      ],
    }
    const s = summarizeRequirements(audit)
    expect(s.headline).toBe('2 of 6 requirements done')
    expect(s.details).toEqual(['2 planned', '2 slots to fill', '2 need attention'])
  })

  it('leaves out empty categories', () => {
    const s = summarizeRequirements({ complete: true, unassigned: [], requirements: [req('a', 'done')] })
    expect(s.headline).toBe('1 of 1 requirements done')
    expect(s.details).toEqual([])
  })
})
