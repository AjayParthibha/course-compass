import { describe, expect, it } from 'vitest'
import { capsIn, capsToSave, creditError, nextTerm, termsAfter } from './settings'

describe('plan settings helpers', () => {
  it('steps through fall and spring terms', () => {
    expect(nextTerm('FA26')).toBe('SP27')
    expect(nextTerm('SP09')).toBe('FA09')
    expect(termsAfter('FA26', 'SP28')).toEqual(['SP27', 'FA27', 'SP28'])
    expect(termsAfter('FA26')).toHaveLength(8)
    expect(termsAfter('FA26').at(-1)).toBe('FA30')
    expect(termsAfter('FA26', 'FA26')).toEqual([])
  })

  it('checks credit fields', () => {
    expect(creditError('')).toBeNull()
    expect(creditError('', true)).toMatch(/Enter/)
    expect(creditError('15')).toBeNull()
    expect(creditError('11')).toMatch(/between 12 and 23/)
    expect(creditError('15.5')).toMatch(/whole number/)
  })

  it('keeps only filled caps for remaining terms', () => {
    expect(capsToSave({ SP27: '15', FA27: '', SP28: '14' }, ['SP27', 'FA27'])).toEqual({ SP27: 15 })
  })

  it('compares saved caps on the remaining terms only', () => {
    // a cap left on the current term doesn't make the form look edited
    expect(capsIn({ FA26: 12, SP27: 15 }, termsAfter('FA26', 'SP28'))).toEqual({ SP27: 15 })
    expect(capsIn({ FA26: 12 }, [])).toEqual({})
  })
})
