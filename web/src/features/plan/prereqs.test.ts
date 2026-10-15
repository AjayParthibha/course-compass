import { describe, expect, it } from 'vitest'
import type { Placement } from '../../api/types'
import { checkPrereqs, type CourseCheck, type GroupCheck, type PrereqExpr } from './prereqs'

const TERMS = ['FA25', 'SP26', 'FA26', 'SP27']

const p = (course: string, term: string, status: Placement['status'] = 'planned'): Placement => ({
  id: course.replace(' ', '').toLowerCase(), term, course, title: null, slot: null, slot_label: null,
  credits: 4, status, locked: false, origin: 'user', counts_as: [],
})

const c = (code: string, concurrent = false): PrereqExpr => ({ kind: 'course', code, concurrent })

// CS 4820: (CS 2800 and CS 3110) or (CS 2110/2112 and CS 2800)
const cs4820: PrereqExpr = {
  kind: 'any',
  items: [
    { kind: 'all', items: [c('CS 2800'), c('CS 3110')] },
    { kind: 'all', items: [{ kind: 'any', items: [c('CS 2110'), c('CS 2112')] }, c('CS 2800')] },
  ],
}

describe('checkPrereqs', () => {
  const target = p('CS 4820', 'FA26', 'in_progress')

  it('marks courses done, planned, too late or missing relative to the target term', () => {
    const plan = [p('CS 2800', 'FA25', 'completed'), p('CS 3110', 'SP27'), target]
    const res = checkPrereqs(cs4820, target, plan, TERMS) as GroupCheck
    const [first, second] = res.items as GroupCheck[]
    expect((first.items[0] as CourseCheck).state).toBe('done')
    expect((first.items[1] as CourseCheck).state).toBe('late')
    expect(first.met).toBe(false)
    const alt = second.items[0] as GroupCheck
    expect(alt.items.map((i) => (i as CourseCheck).state)).toEqual(['missing', 'missing'])
    expect(res.met).toBe(false)
  })

  it('counts equivalents and cross-listings the way the validator does', () => {
    // CS 2800 asks for MATH 1110; an Engineering student took MATH 1910, which counts as it
    const cs2800 = p('CS 2800', 'SP26')
    const math1910 = { ...p('MATH 1910', 'FA25', 'completed'), counts_as: ['MATH 1110', 'MATH 1120'] }
    const res = checkPrereqs(c('MATH 1110'), cs2800, [math1910, cs2800], TERMS) as CourseCheck
    expect(res).toMatchObject({ state: 'done', met: true, via: 'MATH 1910' })

    const direct = checkPrereqs(c('MATH 1910'), cs2800, [math1910, cs2800], TERMS) as CourseCheck
    expect(direct.via).toBeNull()
  })

  it('is met when one alternative is satisfied', () => {
    const plan = [p('CS 2800', 'FA25', 'completed'), p('CS 2110', 'SP26', 'completed'), target]
    const res = checkPrereqs(cs4820, target, plan, TERMS)
    expect(res.met).toBe(true)
  })

  it('accepts concurrent courses in the same term only when allowed', () => {
    const plan = [p('MATH 1920', 'FA26'), target]
    expect(checkPrereqs(c('MATH 1920', true), target, plan, TERMS).met).toBe(true)
    expect(checkPrereqs(c('MATH 1920'), target, plan, TERMS).met).toBe(false)
  })

  it('leaves the outcome open when it depends on a flag', () => {
    const expr: PrereqExpr = { kind: 'any', items: [c('CS 3110'), { kind: 'flag', text: 'permission of instructor' }] }
    expect(checkPrereqs(expr, target, [target], TERMS).met).toBeNull()
    const all: PrereqExpr = { kind: 'all', items: [c('CS 3110'), { kind: 'flag', text: 'permission of instructor' }] }
    expect(checkPrereqs(all, target, [target], TERMS).met).toBe(false)
  })
})
