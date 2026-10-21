import { describe, expect, it } from 'vitest'
import { areaHint, basisLabel } from './reasons'

describe('basisLabel', () => {
  it('dates what the student said', () => {
    expect(basisLabel({ text: 'x', basis: 'stated', fact_id: 1, date: 'Oct 20' })).toEqual({
      kind: 'said',
      text: 'You said · Oct 20',
    })
    expect(basisLabel({ text: 'x', basis: 'stated', fact_id: 1, date: null }).text).toBe('You said')
  })

  it('marks plan reasons and unconfirmed guesses', () => {
    expect(basisLabel({ text: 'x', basis: 'plan', fact_id: null, date: null }).kind).toBe('plan')
    expect(basisLabel({ text: 'x', basis: 'inference', fact_id: 2, date: null })).toEqual({
      kind: 'guess',
      text: 'My guess · not confirmed',
    })
  })
})

describe('areaHint', () => {
  const said = { text: '2 courses about machine learning', basis: 'stated' as const, fact_id: 1, date: 'Oct 20' }

  it('mentions interests only when an area matched one', () => {
    expect(areaHint([{ reasons: [] }, { reasons: [said] }])).toMatch(/interested in/)
    expect(areaHint([{ reasons: [] }])).toBe('Areas that build on your plan come first.')
    expect(areaHint([])).toBe('Areas that build on your plan come first.')
  })
})
