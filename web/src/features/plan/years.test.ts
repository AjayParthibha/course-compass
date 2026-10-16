import { describe, expect, it } from 'vitest'
import { groupByYear } from './years'

describe('groupByYear', () => {
  it('pairs each fall with the following spring', () => {
    expect(groupByYear(['FA24', 'SP25', 'FA25', 'SP26'])).toEqual([
      { start: 24, fall: 'FA24', spring: 'SP25', other: [] },
      { start: 25, fall: 'FA25', spring: 'SP26', other: [] },
    ])
  })

  it('starts a year with no fall when the plan starts in the spring, and keeps summers', () => {
    expect(groupByYear(['SP25', 'SU25', 'FA25'])).toEqual([
      { start: 24, fall: null, spring: 'SP25', other: ['SU25'] },
      { start: 25, fall: 'FA25', spring: null, other: [] },
    ])
  })
})
